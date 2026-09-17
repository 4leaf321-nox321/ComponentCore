"""서버 기동 — 개발에서도, 컨테이너 안에서도 이 파일 하나가 띄운다.

    python run.py                      개발 (reload, 포트 +1 = 8061, 워커 하나 함께)
    APP_ENV=production python run.py   운영 (다중 워커, 8060 — 작업 워커는 systemd 가 따로)

개발이 포트를 +1 하는 이유: 운영과 같은 포트를 쓰면 개발 백엔드를 내린 순간 프론트 프록시가
같은 기계의 운영 설치본에 그대로 붙는다.

## 개발에서는 작업 워커도 함께 띄운다

지그 생성은 큐에 걸리고 워커가 돌린다. 매번 두 터미널에서 두 명령을 치는 것은 곧 안 하게
되고, 그러면 「지그 생성을 눌렀는데 아무 일도 안 일어난다」 를 겪는다. 그래서 개발 모드는
워커를 자식 프로세스로 함께 띄우고 이 프로세스가 끝날 때 같이 내린다. `WORKER_DEV=0` 이면
안 띄운다.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path

import uvicorn

from app.config import get_settings

MCP_DIR = Path(__file__).resolve().parents[1] / "mcp_server"


def _answering(host: str, port: int) -> bool:
    target = "127.0.0.1" if host in ("0.0.0.0", "") else host
    with socket.socket() as probe:
        probe.settimeout(0.3)
        return probe.connect_ex((target, port)) == 0


def _start_worker() -> subprocess.Popen[bytes] | None:
    """개발용 워커 — **코드가 바뀌면 함께 다시 뜬다.**

    uvicorn 의 reload 는 API 만 새로 띄운다. 워커를 그냥 자식으로 두면 옛 코드가 남아, 모델을
    바꾼 뒤 「작업이 queued 에서 안 움직인다」 를 겪는다(실측 — DB 컬럼 하나 지운 뒤 옛 워커가
    매 루프마다 SELECT 에서 죽었다). watchfiles 가 `app/` 을 보다가 바뀌면 워커를 다시 띄운다.
    """
    if os.environ.get("WORKER_DEV") == "0" or get_settings().jobs_inline:
        return None
    child = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "watchfiles",
            "--filter",
            "python",
            f"{sys.executable} -m app.worker",
            "app",
        ]
    )
    print(f"작업 워커(watchfiles): pid {child.pid}", file=sys.stderr)
    return child


def _start_mcp(api_port: int, mcp_port: int) -> subprocess.Popen[bytes] | None:
    """개발용 MCP 서버를 자식으로. 못 띄우는 이유는 **말하고** 건너뛴다 — 조용히 빠지면
    「Claude 가 안 붙는다」 를 여기서 찾을 사람이 없다."""
    if os.environ.get("MCP_DEV") == "0":
        return None
    python = MCP_DIR / "venv" / "bin" / "python"
    server = MCP_DIR / "server.py"
    if not python.exists() or not server.exists():
        print(
            f"MCP 서버는 안 띄웁니다 — {python} 이 없습니다. (cd mcp_server && "
            "python3 -m venv venv && ./venv/bin/pip install -r requirements.txt)",
            file=sys.stderr,
        )
        return None
    if _answering("127.0.0.1", mcp_port):
        print(
            f"MCP 서버는 안 띄웁니다 — {mcp_port} 포트에 이미 응답하는 것이 있습니다.",
            file=sys.stderr,
        )
        return None
    env = {
        **os.environ,
        "PLATFORM_API_BASE": f"http://127.0.0.1:{api_port}",
        "MCP_HOST": "127.0.0.1",
        "MCP_PORT": str(mcp_port),
        "APP_SLUG": get_settings().app_slug,
    }
    child = subprocess.Popen([str(python), str(server)], cwd=MCP_DIR, env=env)
    print(f"MCP 서버: http://127.0.0.1:{mcp_port}/mcp → 백엔드 http://127.0.0.1:{api_port}")
    return child


def _stop(child: subprocess.Popen[bytes] | None) -> None:
    if child is None or child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=10)
    except subprocess.TimeoutExpired:
        child.kill()


def main() -> None:
    settings = get_settings()
    development = settings.app_env == "development"
    port = settings.port + 1 if development else settings.port

    if development and _answering(settings.host, port):
        raise SystemExit(
            f"{port} 포트에 이미 응답하는 서버가 있습니다.\n  ss -ltnp 'sport = :{port}'\n"
            "으로 잡고 있는 프로세스를 찾아 내린 뒤 다시 돌리세요."
        )

    if development:
        worker = _start_worker()
        mcp = _start_mcp(port, settings.port + 2)
        try:
            uvicorn.run("app.main:app", host=settings.host, port=port, reload=True)
        finally:
            _stop(worker)
            _stop(mcp)
    else:
        uvicorn.run(
            "app.main:app",
            host=settings.host,
            port=port,
            workers=settings.uvicorn_workers,
            proxy_headers=settings.trust_proxy,
            forwarded_allow_ips="*" if settings.trust_proxy else None,
        )


if __name__ == "__main__":
    main()
