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
from app.modules.jobs import services

logger = logging.getLogger("app.worker")

POLL_SECONDS = 1.0
STALE_CHECK_EVERY = 60


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
                    last_stale = time.monotonic()

                job = services.claim_next(db, self.worker_id)
                if job is None:
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
