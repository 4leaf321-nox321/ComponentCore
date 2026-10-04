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
import os
import re
import shutil
import time
import uuid
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


#: 쓰는 중인 것의 표시 — 점으로 시작하는 이름은 해석 쪽 탐색기가 보지 않는다(SimEngBay 의
#: `core/doe/browse.py`). 다 쓴 뒤 제 이름으로 바꾼다.
PARTIAL = ".partial-"


def _partial(path: Path) -> Path:
    return path.with_name(f".{path.name}{PARTIAL}{uuid.uuid4().hex[:8]}")


def publish(source: Path, target: Path) -> None:
    """서버 보관 폴더를 공유 폴더로 — **읽는 쪽이 반쪽을 보지 않게.**

    처음 보낼 때는 숨긴 이름에 다 쓴 뒤 이름을 바꾼다 — 폴더가 보이는 순간 다 있다. 복사하는
    동안 해석 쪽이 폴더를 열면 STEP 이 덜 온 점을 「짝이 없다」 고 읽었다.

    다시 보낼 때(점을 더한 뒤)는 폴더를 갈아 끼우지 않는다 — 해석 쪽이 그 폴더에 덧붙인 것을
    지우지 않게, 그리고 열려 있는 폴더의 이름을 바꾸다 실패하지 않게. 대신 점 파일 · 형상을
    먼저 쓰고 위의 파일(표 · `study.json` …)은 파일마다 숨긴 이름에 쓴 뒤 바꿔 끼우며, 표
    (`manifest.csv`)를 **맨 나중에** 둔다 — 표가 가리키는 파일은 늘 이미 있다."""
    if not target.exists():
        staging = _partial(target)
        try:
            shutil.copytree(source, staging)
            try:
                staging.rename(target)
                return
            except OSError:
                if not target.exists():
                    raise
                # 그사이 다른 요청이 같은 폴더를 냈다 — 아래처럼 덮어 쓴다.
                source = staging
            _overlay(source, target)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        return
    _overlay(source, target)


def _overlay(source: Path, target: Path) -> None:
    for child in sorted(source.iterdir()):
        if child.is_dir():
            shutil.copytree(child, target / child.name, dirs_exist_ok=True)
    tops = [one for one in source.iterdir() if one.is_file()]
    for one in sorted(tops, key=lambda path: (path.name == "manifest.csv", path.name)):
        temp = _partial(target / one.name)
        shutil.copy2(one, temp)
        os.replace(temp, target / one.name)


def sweep_partials(root: Path, *, older_than_s: float = 86400) -> list[str]:
    """쓰다 만 것(서버가 복사 도중 멈췄다)을 치운다 — 하루가 지난 숨긴 `…partial-…` 만.
    지금 쓰는 중인 것은 건드리지 않는다."""
    if not root.is_dir():
        return []
    cutoff = time.time() - older_than_s
    removed: list[str] = []
    for path in [*root.glob(f".*{PARTIAL}*"), *root.glob(f"*/.*{PARTIAL}*")]:
        try:
            if path.stat().st_mtime > cutoff:
                continue
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
            removed.append(str(path))
        except OSError:
            continue
    return removed


def windows_path(path: Path) -> str:
    """화면에 보여 줄 경로. 서버는 WSL 에서 `/mnt/f/...` 로 쓰지만 사람은 `F:\\...` 로 연다."""
    text = str(path)
    if text.startswith("/mnt/") and len(text) > 6 and text[6] == "/":
        return f"{text[5].upper()}:\\" + text[7:].replace("/", "\\")
    return text


def manifest_columns(
    factor_names: list[str],
    measure_names: list[str] | None = None,
    *,
    midsurface: bool = False,
) -> list[str]:
    """표의 열 — 되짚는 열쇠(번호 · 상태), 바꾼 변수, 파일, 실패 사유. 해석 결과 열은 해석이
    붙인다.

    `point_file` · `unresolved` 는 **해석이 이 점을 쓸 수 있는가**를 말한다. 영역을 하나도 못
    풀었으면 경계조건을 붙일 자리가 없고, 그 사실은 표에서 한눈에 보여야 한다 — 설계점 200개를
    보내 놓고 「왜 절반이 실패했지」 를 로그에서 찾게 하지 않는다."""
    return [
        "point",
        "status",
        *factor_names,
        # 측정값 — 형상에서 바로 나오는 값(부피 · 크기 · 거리 · 식). 고른 것만.
        *(measure_names or []),
        "step_file",
        # 중간면(셸 해석용) — 고른 스터디만. 판이 아닌 점은 빈 칸(까닭은 warnings).
        *(["mid_file"] if midsurface else []),
        "point_file",
        "unresolved",
        "interference",
        "warnings",
        "error",
    ]


def manifest_row(
    number: int,
    params: dict[str, Any],
    factor_names: list[str],
    *,
    status: str,
    step_file: str = "",
    error: str = "",
    interference: dict[str, Any] | None = None,
    point_file: str = "",
    unresolved: list[str] | None = None,
    warnings: list[str] | None = None,
    measures: dict[str, Any] | None = None,
    mid_file: str = "",
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
        # 못 잰 값은 빈 칸 — 0 으로 적으면 「질량 0」 인 점이 최적으로 뽑힌다.
        **{name: ("" if value is None else value) for name, value in (measures or {}).items()},
        "step_file": step_file,
        "mid_file": mid_file,
        "point_file": point_file,
        # 못 푼 영역 이름을 **그대로** 적는다 — 개수만 적으면 어느 것이 빠졌는지
        # 다시 물어야 한다.
        "unresolved": " ".join(unresolved or []),
        "interference": collision,
        # 형상 점검 — 메시가 막힐 자리(얇은 벽 · 짧은 모서리 · 좁은 면 · 쪼개진 바디).
        # 비면 통과.
        "warnings": " / ".join(warnings or []),
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
    # 제약식 — 범위 안이라도 이 조건을 어긴 조합은 만들지 않았다(만들기 전에 걸렀다).
    constraints = (
        "\n제약(위반하는 조합은 생성하지 않았습니다)\n"
        + "\n".join(f"  - {one}" for one in study.get("constraints") or [])
        + "\n"
        if study.get("constraints")
        else ""
    )
    # 중간면 — 고른 스터디만. 셸 요소로 푸는 쪽이 읽는다.
    mid = (
        "  <형상>_mid.step   중간면: 두께 중앙의 면입니다(셸 요소용). 각 판의 두께는\n"
        "                    점 파일의 `midsurface`, 표의 `mid_file`에 있습니다. 판이 아닌\n"
        "                    점은 비어 있으며, 사유는 warnings에 있습니다.\n"
        if "midsurface" in (study.get("outputs") or [])
        else ""
    )
    # 복제한 DOE — 원본과 점끼리 견줄 수 있다는 것을 폴더만 보고 알게.
    origin = study.get("cloned_from")
    cloned = ""
    if isinstance(origin, dict):
        owner = (origin.get("owner") or {}).get("name", "")
        cloned = (
            f"\n복제 원본: ‘{origin.get('name', '')}’({owner}) — "
            "설계점 번호와 값이 원본과 같습니다.\n"
        )
    text = f"""{study.get("name", "DOE")}
{"=" * 60}

{study.get("description", "") or "(설명 없음)"}
{cloned}
생성일: {datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M")}
방법: {_method_text(str(study.get("method") or ""))}
설계점: {point_count}개
시드: {study.get("seed")}   ← 같은 표를 다시 생성할 때 사용합니다.

변경한 치수
{factors or "  (없음)"}
{constraints}
파일
  manifest.csv   설계점별 변경한 변수 값, 파일 이름, 상태, 형상 점검 경고(warnings)
  study.json     기준 레시피와 전체 인자 정의(다시 생성할 때 사용)
  conditions.json  해석 조건 전체: 선택 그룹, 구속, 하중, 접촉, 초기 조건, 해석 설정, 물성
                   (숫자 필드에 "=식"이 있을 수 있으며, 계산된 값은 점 파일에 있습니다)
  points/        p0001.step   형상(해당 점에서만 사용하는 형상)
                 p0001.json   해당 점의 전체 정보: 변수 값, 영역과 바디의 좌표 지문,
                              해당 변수로 계산된 조건, 이 점이 사용하는 STEP 파일,
                              형상 점검(quality: 최소 벽 두께, 짧은 모서리, 좁은 면)
  shapes/        <지문>.step  여러 점이 공유하는 형상입니다. 조건만 변경하면(압력 2, 3 MPa)
                              모든 점의 형상이 같으므로 하나만 저장합니다. 이 폴더가 없으면
                              점마다 형상이 다릅니다.
{mid}
각 점이 사용하는 STEP 파일은 표와 점 파일의 `step_file`에 기록되어 있습니다. 파일 이름으로
추정하지 마십시오. 같은 STEP 파일을 사용하는 점들은 메시를 한 번만 생성하면 됩니다.

STEP은 mm 단위이며, 변경하지 않은 치수(연결부 등)는 모든 점에서 동일합니다.
해석 결과는 이 폴더로 반환되지 않습니다. 해석을 수행하는 쪽에서 결과를 보관하고 조회합니다.
"""
    path = folder / "README.txt"
    path.write_text(text, encoding="utf-8")
    return path


#: 방식의 사람 말.
METHOD_TEXT = {
    "factorial": "전체 조합",
    "lhs": "라틴 하이퍼큐브(LHS)",
    "table": "직접 입력한 표(입력값을 그대로 사용하며 가공 단위로 맞추지 않음)",
    "oat": "하나씩 변경(OAT: 중심점에서 변수별로 각 값을 적용)",
    "ccd": "중심 합성(면 중심 CCF: 모서리, 축, 중심점)",
    "bbd": "Box-Behnken(변수 2개씩 양 끝, 나머지는 중심값)",
    "sobol": "Sobol 수열(시드로 디지털 이동, 이어서 추출하면 수열이 이어짐)",
}


def _method_text(method: str) -> str:
    return METHOD_TEXT.get(method, method)


def _factor_text(factor: dict[str, Any]) -> str:
    mode = factor.get("mode")
    if mode == "range":
        return f"{factor.get('start')} ~ {factor.get('end')} ({factor.get('steps')}단계)"
    if mode == "list":
        return ", ".join(str(v) for v in factor.get("values", []))
    return f"고정 {factor.get('value')}"
