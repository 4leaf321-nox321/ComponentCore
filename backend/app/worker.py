"""작업 워커 — queued 를 집어 돌린다.

    python -m app.worker            # 하나. 더 돌리면 그만큼 동시에 돈다(SKIP LOCKED)

지그 생성은 CPU 를 쓰는 동기 일이라 프로세스 하나가 한 번에 하나만 한다. 개발에서는 run.py 가
자식으로 하나 띄운다. 운영에서는 systemd 유닛(<slug>-worker)이 띄운다.
"""

from __future__ import annotations

import logging
import os
import signal
import socket
import threading
import time
import uuid
from types import FrameType

from app import handlers, version
from app.config import get_settings
from app.database import SessionLocal
from app.logging_setup import setup_logging
from app.modules.audit import retention
from app.modules.jobs import services
from app.modules.tasks import services as tasks
from app.modules.webhooks import services as webhooks

logger = logging.getLogger("app.worker")

POLL_SECONDS = 1.0
STALE_CHECK_EVERY = 60


class PlatformChores:
    """StandardPlatform 에서 들인 **데이터 작업(tasks)의 살림** — SP `worker.py` 의
    `_tick_housekeeping` 그대로(ADR 0008). 형상 작업(jobs)과 큐는 다르고 워커는 하나다: 루프가
    형상 작업을 먼저 집고, 없으면 데이터 작업 하나를 돌린다(`tasks.process_one`).

    빼 둔 것: 요청 시간 기록 지우기(그 화면 · 기록을 아직 안 들였다), 알림 연결로 바로 깨기
    (CompCore 워커는 1초마다 묻는다)."""

    HEARTBEAT_EVERY = 30.0
    RECOVER_EVERY = 60.0
    PURGE_EVERY = 3600.0
    GC_FIRST_AFTER = 3600.0

    def __init__(self, worker_id: str) -> None:
        self.worker_id = worker_id
        now = time.monotonic()
        self._last_beat = 0.0
        self._last_recover = 0.0
        self._last_purge = 0.0
        self._last_webhook = 0.0
        hours = get_settings().filestore_gc_hours
        self._gc_every = hours * 3600.0 if hours > 0 else 0.0
        self._last_gc = now - max(self._gc_every - self.GC_FIRST_AFTER, 0.0)
        self._gc_thread: threading.Thread | None = None

    @staticmethod
    def retry_webhooks() -> None:
        """**밀린 웹훅은 여기서 다시 살아난다**(프로세스 안 타이머는 재시작에 사라진다)."""
        with SessionLocal() as db:
            if webhooks.pending_count(db):
                webhooks.enqueue_dispatch(db)

    def tick(self) -> None:
        now = time.monotonic()
        if now - self._last_beat >= self.HEARTBEAT_EVERY:
            tasks.heartbeat(self.worker_id, None)
            self._last_beat = now
        if now - self._last_recover >= self.RECOVER_EVERY:
            with SessionLocal() as db:
                revived = tasks.recover_stale(db)
            if revived:
                logger.warning("멎은 데이터 작업 %d개를 되살렸습니다", revived)
            self._last_recover = now
        if now - self._last_webhook >= webhooks.RETRY_AFTER_SECONDS:
            self.retry_webhooks()
            self._last_webhook = now
        if now - self._last_purge >= self.PURGE_EVERY:
            with SessionLocal() as db:
                gone = tasks.purge_expired_files(db)
                old_tasks = tasks.purge_old_jobs(db)
                old_graves = tasks.purge_old_tombstones(db)
                old_undo = tasks.purge_old_undo_journals(db)
                # 접근 로그는 보관 기간이 지난 것만. 감사 기록은 안 지운다.
                old_access = retention.purge_old_access_logs(db)
            if gone or old_tasks or old_graves or old_undo or old_access:
                logger.info(
                    "정리: 작업 파일 %d개 · 끝난 데이터 작업 %d개 · 끊긴 선의 무덤 %d개 · "
                    "되돌릴 기록 %d줄 · 접근 로그 %d줄",
                    gone,
                    old_tasks,
                    old_graves,
                    old_undo,
                    old_access,
                )
            self._last_purge = now
        if self._gc_every and now - self._last_gc >= self._gc_every:
            # **따로 돈다** — 큰 저장소를 훑는 동안 바퀴(박동 · 작업)가 멎지 않게.
            self._last_gc = now
            if self._gc_thread is None or not self._gc_thread.is_alive():
                self._gc_thread = threading.Thread(
                    target=_clean_orphans, name="filestore-gc", daemon=True
                )
                self._gc_thread.start()

    def run_one(self) -> bool:
        """데이터 작업 하나 — 돌렸으면 True(박동은 `process_one` 이 끝에서 남긴다)."""
        worked = tasks.process_one(self.worker_id)
        if worked:
            self._last_beat = time.monotonic()
        return worked


def _clean_orphans() -> None:
    """고아 첨부 정리 한 차례 — 바퀴와 **다른 스레드**에서(제 세션으로)."""
    from app.modules.files import gc

    try:
        with SessionLocal() as db:
            done = gc.clean(db, gc.scan(db))
    except Exception:
        logger.exception("고아 첨부 정리 실패 — 다음 차례에 다시")
        return
    if done.files or done.temp:
        logger.info("고아 첨부 정리: 파일 %d개 · 임시 파일 %d개", done.files, done.temp)


class Worker:
    def __init__(self) -> None:
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}"
        self.stopping = False
        #: 신호 줄이 읽는 지금 상태 — 루프가 바꾸고 신호 줄이 적는다.
        self.state = "idle"
        self.current_job_id: uuid.UUID | None = None
        self._beating = threading.Event()

    def stop(self, signum: int, _frame: FrameType | None) -> None:
        logger.info("종료 신호 %s — 지금 작업을 끝내고 멈춥니다.", signum)
        self.stopping = True
        self.state = "stopping" if self.current_job_id else "stopped"

    def _beat(self) -> None:
        """**살아 있다는 신호**를 적는다 — 루프가 작업 하나에 몇 분 묶여 있어도 이 줄은 따로
        돈다. 신호가 끊기면 서버 화면이 「응답 없음」 으로 보이고, 잡고 있던 작업은 다른 워커가
        되살린다. 적다가 실패해도(DB 가 잠깐 끊김) 워커를 죽이지 않는다."""
        while not self._beating.is_set():
            db = SessionLocal()
            try:
                services.beat(
                    db,
                    self.worker_id,
                    state=self.state,
                    current_job_id=self.current_job_id,
                    hostname=socket.gethostname(),
                    pid=os.getpid(),
                    version=version.current(),
                )
            except Exception:
                logger.warning("워커 신호를 적지 못했습니다 — 다음에 다시.", exc_info=True)
            finally:
                db.close()
            self._beating.wait(services.BEAT_EVERY)

    def run(self) -> None:
        handlers.register_all()
        # **앱과 같은 조립** — 들인 모듈의 레지스트리(확장 지점 · 시스템 출처 · 이벤트)를
        # 워커도 채운다. 비어 있으면 처리 함수가 등록을 부르는 자리에서 조용히 다른 길로
        # 간다(SP 실측, 2026-10-10).
        from app.main import register_platform

        register_platform()
        chores = PlatformChores(self.worker_id)
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        logger.info("워커 시작 (%s)", self.worker_id)
        beater = threading.Thread(target=self._beat, name="worker-beat", daemon=True)
        beater.start()

        last_stale = 0.0
        while not self.stopping:
            db = SessionLocal()
            try:
                if time.monotonic() - last_stale > STALE_CHECK_EVERY:
                    revived = services.requeue_stale(db)
                    if revived:
                        logger.warning("갇힌 작업 %d 건을 되살렸습니다.", revived)
                    services.prune_workers(db)
                    last_stale = time.monotonic()

                chores.tick()
                job = services.claim_next(db, self.worker_id)
                if job is None:
                    # 형상 작업이 없으면 데이터 작업(가져오기 · 동기화 · 내보내기 …) 하나.
                    if not chores.run_one():
                        time.sleep(POLL_SECONDS)
                    continue
                logger.info("작업 시작 %s (%s)", job.id, job.kind)
                self.current_job_id = job.id
                self.state = "busy"
                try:
                    done = services.execute(db, job, worker_id=self.worker_id)
                finally:
                    self.current_job_id = None
                    self.state = "stopping" if self.stopping else "idle"
                logger.info("작업 %s → %s", done.id, done.status)
            except Exception:
                # DB 가 잠깐 끊긴 것 같은 일. 죽지 말고 잠시 뒤 다시.
                logger.exception(
                    "워커 루프 오류 — %.0f초 뒤 다시 시도합니다.", POLL_SECONDS * 5
                )
                time.sleep(POLL_SECONDS * 5)
            finally:
                db.close()
        # 멈췄다고 마지막으로 적는다 — 안 적으면 2분 뒤 「응답 없음」 으로 보인다.
        self._beating.set()
        db = SessionLocal()
        try:
            services.beat(db, self.worker_id, state="stopped")
        except Exception:
            logger.warning("멈춤을 적지 못했습니다.", exc_info=True)
        finally:
            db.close()
        logger.info("워커 종료")


def main() -> None:
    settings = get_settings()
    setup_logging(settings)
    Worker().run()


if __name__ == "__main__":
    main()
