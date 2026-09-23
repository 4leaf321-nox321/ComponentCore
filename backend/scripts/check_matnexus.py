"""물성 플랫폼(MatNexus)에 닿나 — **설치하는 자리에서 한 줄로 본다.**

    .venv/bin/python scripts/check_matnexus.py

물성 탐색기가 안 뜨는 까닭은 셋뿐이다: 주소가 없다 · 망이 안 닿는다 · 토큰이 거절됐다.
화면에서는 「올려 둔 카탈로그로 고르는 중」 이라고만 보이므로(그게 맞다 — 작업이 멈추면 안
된다), 어느 쪽인지 묻는 자리가 따로 있어야 한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.shared.clients import matnexus


def main() -> int:
    settings = get_settings()
    print(f"주소 : {settings.matnexus_base_url or '(비어 있음)'}")
    token = settings.matnexus_token
    print(f"토큰 : {'있음(' + token[:12] + '…)' if token else '(비어 있음)'}")

    got = matnexus.ping()
    if not got["configured"]:
        print(f"\n결과 : 설정 안 됨 — {got['detail']}")
        print("       이대로면 물성 탐색기는 올려 둔 카탈로그 파일로만 돕니다.")
        return 1
    if not got["ok"]:
        print(f"\n결과 : 못 닿음 — {got['detail']}")
        print("       방화벽(8010 · 8011 인바운드) · 주소 · 토큰을 차례로 보세요.")
        return 2

    rows = matnexus.search(limit=3)
    print(f"\n결과 : 닿음 — {got['detail']}")
    for one in rows:
        name = one.get("record_name") or one.get("name") or "?"
        print(f"       {one.get('code', '?'):12} {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
