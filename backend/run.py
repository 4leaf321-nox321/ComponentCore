"""서버 기동 — 개발에서도, 컨테이너 안에서도 이 파일 하나가 띄운다.

    python run.py                      개발 (reload, 포트 +1 = 8051)
    APP_ENV=production python run.py   운영 (다중 워커, 8050)

개발이 포트를 +1 하는 이유: 운영과 같은 포트를 쓰면 개발 백엔드를 내린 순간 프론트 프록시가
같은 기계의 운영 설치본에 그대로 붙는다.
"""

from __future__ import annotations

import socket

import uvicorn

from app.config import get_settings


def _answering(host: str, port: int) -> bool:
    target = "127.0.0.1" if host in ("0.0.0.0", "") else host
    with socket.socket() as probe:
        probe.settimeout(0.3)
        return probe.connect_ex((target, port)) == 0


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
        uvicorn.run("app.main:app", host=settings.host, port=port, reload=True)
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
