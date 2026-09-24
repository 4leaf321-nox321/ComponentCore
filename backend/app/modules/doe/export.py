"""공유 폴더로 내보내기 — **해석(ANSYS)이 읽는 것은 이 폴더다.**

폴더 하나가 곧 한 번의 DOE 다:

    73_AutoJigGenerator/브래킷_튜닝-3f9a21/
    ├─ manifest.csv   설계점 · 바꾼 변수 값 · 파일 이름 · 상태
    ├─ study.json     기준 레시피 · 인자 정의 · 시드(같은 표를 다시 만들 때)
    ├─ README.txt     사람이 열어 볼 한 장
    ├─ points/p0001.step · p0001.json …
    └─ shapes/<지문>.step   **여러 점이 나눠 쓰는 형상**(조건만 훑었을 때). 없을 수도 있다

CSV 를 정본으로 두는 이유: 해석 쪽에서 파일 이름만 보고 치수를 되짚을 수 없다. 번호 → 치수 →
결과를 잇는 표가 한 장 있어야 형상과 해석 결과가 붙는다.
"""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

#: 폴더 · 파일 이름에 쓸 수 없는 글자. 윈도우 공유 폴더로 가므로 윈도우 규칙을 따른다.
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_name(name: str) -> str:
    """사람이 붙인 이름을 폴더 이름으로. 한글은 그대로 두고 금지 글자만 바꾼다."""
    cleaned = _UNSAFE.sub("_", name).strip().strip(".")
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned[:60] or "doe"


def study_dir(root: Path, name: str, study_id: str) -> Path:
    """DOE 마다 제 폴더. 이름이 겹쳐도 id 앞 8자로 갈린다 — 덮어쓰지 않는다."""
    return root / f"{safe_name(name)}-{study_id[:8]}"


def windows_path(path: Path) -> str:
    """화면에 보여 줄 경로. 서버는 WSL 에서 `/mnt/f/...` 로 쓰지만 사람은 `F:\\...` 로 연다."""
    text = str(path)
    if text.startswith("/mnt/") and len(text) > 6 and text[6] == "/":
        return f"{text[5].upper()}:\\" + text[7:].replace("/", "\\")
    return text


def manifest_columns(factor_names: list[str]) -> list[str]:
    """표의 열 — 되짚는 열쇠(번호 · 상태), 바꾼 변수, 파일, 실패 사유. 해석 결과 열은 해석이
    붙인다.

    `point_file` · `unresolved` 는 **해석이 이 점을 쓸 수 있는가**를 말한다. 영역을 하나도 못
    풀었으면 경계조건을 붙일 자리가 없고, 그 사실은 표에서 한눈에 보여야 한다 — 설계점 200개를
    보내 놓고 「왜 절반이 실패했지」 를 로그에서 찾게 하지 않는다."""
    return [
        "point",
        "status",
        *factor_names,
        "step_file",
        "point_file",
        "unresolved",
        "interference",
        "error",
    ]


def manifest_row(
    number: int,
    params: dict[str, float],
    factor_names: list[str],
    *,
    status: str,
    step_file: str = "",
    error: str = "",
    interference: dict[str, Any] | None = None,
    point_file: str = "",
    unresolved: list[str] | None = None,
) -> dict[str, Any]:
    # 조립이면 겹침 — ok 또는 「N건 (총 부피)」. 구성품이 하나면 빈 칸.
    if interference is None:
        collision = ""
    elif interference.get("ok"):
        collision = "ok"
    else:
        bad = [one for one in interference.get("items", []) if not one.get("ok")]
        collision = f"{len(bad)} ({interference.get('total_volume', 0)} mm3)"
    return {
        "point": number,
        "status": status,
        **{name: params.get(name, "") for name in factor_names},
        "step_file": step_file,
        "point_file": point_file,
        # 못 푼 영역 이름을 **그대로** 적는다 — 개수만 적으면 어느 것이 빠졌는지
        # 다시 물어야 한다.
        "unresolved": " ".join(unresolved or []),
        "interference": collision,
        "error": error,
    }


def to_csv(columns: list[str], rows: list[dict[str, Any]]) -> str:
    """엑셀이 바로 여는 CSV. 한글이 깨지지 않게 BOM 을 붙인다."""
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=columns, extrasaction="ignore", lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    return "\ufeff" + buffer.getvalue()


def write_manifest(folder: Path, columns: list[str], rows: list[dict[str, Any]]) -> Path:
    path = folder / "manifest.csv"
    path.write_text(to_csv(columns, rows), encoding="utf-8")
    return path


def write_study(folder: Path, study: dict[str, Any]) -> Path:
    path = folder / "study.json"
    path.write_text(json.dumps(study, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_conditions(folder: Path, conditions: dict[str, Any]) -> Path | None:
    """스터디의 해석 조건 — **식이 있는 그대로**(사람이 읽는 정본).

    설계점마다 **풀린** 값은 그 점의 `points/pNNNN.json` 안에 있다. 받는 쪽은 식을 풀 수
    없기 때문이다 — 그렇다고 이 파일을 안 쓰면 「무엇을 훑은 조건인가」 가 사라진다.
    """
    if not conditions:
        return None
    path = folder / "conditions.json"
    path.write_text(json.dumps(conditions, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_readme(folder: Path, study: dict[str, Any], point_count: int) -> Path:
    """사람이 폴더를 열었을 때 한 장으로 아는 것 — 무엇을 왜 바꿨는지."""
    factors = "\n".join(
        f"  - {one['name']}: " + _factor_text(one) for one in study.get("factors", [])
    )
    text = f"""{study.get("name", "DOE")}
{"=" * 60}

{study.get("description", "") or "(설명 없음)"}

만든 때: {datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M")}
방법: {"전체 조합" if study.get("method") == "factorial" else "라틴 하이퍼큐브(LHS)"}
설계점: {point_count} 개
시드: {study.get("seed")}   ← 같은 표를 다시 만들 때 쓴다

바꾼 치수
{factors or "  (없음)"}

파일
  manifest.csv   설계점마다 바꾼 변수 값 · 파일 이름 · 상태
  study.json     기준 레시피와 인자 정의 전부(다시 만들 때)
  conditions.json  해석 조건 한 벌 — 선택 그룹 · 구속 · 하중 · 접촉 · 초기 · 해석 설정 · 물성
                   (숫자 칸에 "=식" 이 있을 수 있다. 푼 값은 점 파일 안에)
  points/        p0001.step   형상 (그 점만 쓰는 것)
                 p0001.json   이 점의 모든 것 — 변수 값 · 영역과 바디의 좌표 지문 ·
                              그 변수로 **풀린** 조건 · 이 점이 쓰는 STEP 파일
  shapes/        <지문>.step  **여러 점이 나눠 쓰는 형상.** 조건만 훑으면(압력 2 · 3 MPa)
                              형상이 모든 점에서 같으므로 한 벌만 둔다. 이 폴더가 없으면
                              점마다 형상이 다른 것이다.

어느 점이 어느 STEP 을 쓰는지는 **표와 점 파일의 `step_file`** 이 말한다 — 파일 이름을
짐작하지 마라. 같은 STEP 을 가리키는 점들은 메시도 한 번만 만들면 된다.

STEP 은 mm 단위이며, 바꾸지 않은 치수(연결부 등)는 모든 점에서 똑같다.
해석 결과는 이 폴더로 돌아오지 않는다 — 푸는 쪽이 들고 거기서 본다.
"""
    path = folder / "README.txt"
    path.write_text(text, encoding="utf-8")
    return path


def _factor_text(factor: dict[str, Any]) -> str:
    mode = factor.get("mode")
    if mode == "range":
        return f"{factor.get('start')} ~ {factor.get('end')} ({factor.get('steps')} 단계)"
    if mode == "list":
        return ", ".join(str(v) for v in factor.get("values", []))
    return f"고정 {factor.get('value')}"
