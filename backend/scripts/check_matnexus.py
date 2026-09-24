"""물성 플랫폼(MatNexus)에 닿나 — **설치하는 자리에서 한 줄로 본다.**

    .venv/bin/python scripts/check_matnexus.py

물성 탐색기가 안 뜨는 까닭은 셋뿐이다: 주소가 없다 · 망이 안 닿는다 · 토큰이 거절됐다.
화면에서는 「올려 둔 카탈로그로 고르는 중」 이라고만 보이므로(그게 맞다 — 작업이 멈추면 안
된다), 어느 쪽인지 묻는 자리가 따로 있어야 한다.

**닿는 것만으로는 부족하다**(2026-09-24 권한 개편에서 배웠다). MatNexus 는 부서 트리로 권한을
나누고 PAT 에는 범위가 없다 — 그래서 **무엇이 보이나는 그 토큰이 누구냐**로 정해진다. 붙기는
붙는데 계정이 달라 하나도 안 보이거나, 반대로 시스템 관리자 토큰이라 전부 보이는 일이 생긴다.
그래서 이 스크립트는 **누구로 붙었는지**까지 말한다.

그리고 **단위계가 그쪽과 같은 말을 하는지** 맞춰 본다. MatNexus 는 단위계를 1급으로 들고
있고(`/api/fitting/unit-systems`) 우리도 제 표를 든다 — 런타임에 그쪽을 의존하지 않으려는
것이다(꺼져 있어도, 올려 둔 사본으로 골라도 내보내기는 돼야 한다). 대신 **어긋나면 여기서
말한다.** 물성 값이 조용히 다른 단위로 나가는 것보다는 낫다.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.shared.clients import matnexus
from app.shared.errors import AppError


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

    print("\n결과 : 닿음")
    print(f"계정 : {got.get('account') or '(모름)'}")
    print(f"부서 : {got.get('workspace') or '(좁히지 않음 — 그 계정이 보는 전부)'}")
    print(f"재료 : {got.get('materials')}건")

    # **과한 권한은 조용히 지나가면 안 된다.** 읽기만 하는 연동에 시스템 관리자 토큰을 꽂아
    # 두면, MatNexus 가 부서로 나눠 둔 권한을 이쪽에서 통째로 우회한다.
    if got.get("system_admin"):
        print(
            "\n⚠ 시스템 관리자 토큰입니다 — 읽기만 하는 연동에는 과합니다.\n"
            "  MatNexus 에서 **읽기 전용 계정**을 만들어 필요한 부서에만 넣고, 그 계정의\n"
            "  토큰을 MATNEXUS_TOKEN 에 두는 것이 맞습니다. 부서를 더 좁히려면\n"
            "  MATNEXUS_WORKSPACE=<부서 slug>."
        )
    elif got.get("materials") == 0:
        print(
            "\n⚠ 보이는 재료가 없습니다 — 이 계정이 속한 부서에 재료가 없습니다.\n"
            "  MatNexus 에서 그 계정을 재료가 있는 부서에 넣어 주세요."
        )

    # **단위계가 그쪽과 같은 말을 하나.** 그쪽은 지금도 고쳐지고 있다(이 대화 중에
    # `density_si` 칸이 생겼다) — 사람이 눈으로 맞춰 보는 것은 오래 못 간다.
    from app.core import units_check

    try:
        같나 = units_check.compare(matnexus.unit_systems())
    except (matnexus.MatNexusUnavailable, AppError) as failure:
        print(f"\n단위계 : 못 맞춰 봤습니다 — {failure}")
    else:
        if 같나["ok"]:
            print(f"\n단위계 : 같은 말을 합니다 ({' · '.join(같나['compared'])})")
        else:
            print("\n단위계 : **어긋납니다** — 환산한 물성이 그쪽과 다르게 나갑니다")
            for one in 같나["problems"]:
                print(f"       ⚠ {one}")

    rows = matnexus.search(limit=3)
    print()
    for one in rows:
        name = one.get("record_name") or one.get("name") or "?"
        room = one.get("owner_workspace_name") or "?"
        print(f"       {one.get('code', '?'):12} {name:40} ← {room}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
