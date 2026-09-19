"""공유 폴더로 내보내기 — **해석(ANSYS)이 읽는 것은 이 폴더다.**

폴더 하나가 곧 한 번의 DOE 다:

    73_AutoJigGenerator/브래킷_튜닝-3f9a21/
    ├─ manifest.csv   설계점 · 바꾼 변수 값 · 파일 이름 · 상태 (해석 결과는 여기에 붙인다)
    ├─ study.json     기준 레시피 · 인자 정의 · 시드(같은 표를 다시 만들 때)
    ├─ README.txt     사람이 열어 볼 한 장
    └─ points/p0001.step …

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
    붙인다."""
    return ["point", "status", *factor_names, "step_file", "error"]


def manifest_row(
    number: int,
    params: dict[str, float],
    factor_names: list[str],
    *,
    status: str,
    step_file: str = "",
    error: str = "",
) -> dict[str, Any]:
    return {
        "point": number,
        "status": status,
        **{name: params.get(name, "") for name in factor_names},
        "step_file": step_file,
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
  manifest.csv   설계점마다 바꾼 변수 값 · 파일 이름 · 상태. **해석 결과를 이 표에 붙인다.**
  study.json     기준 레시피와 인자 정의 전부(다시 만들 때)
  points/        p0001.step … 번호가 manifest 의 point 열과 같다

STEP 은 mm 단위이며, 바꾸지 않은 치수(연결부 등)는 모든 점에서 똑같다.
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
