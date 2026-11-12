"""STEP 가져오기 — **무엇이 오든 바디로 가른다**(`import_step` 의 `bodies: "leaf"`).

build123d 의 `import_step` 은 STEP 의 조립 트리를 자식으로 돌려준다 — 부품마다 제품 이름이
이름표다. 맨 위 한 층만 보던 옛 규칙(`"top"`)은 실측(2026-11-12)에서 이렇게 어긋났다:

- 한 부품에 솔리드 여럿(멀티바디 파트) → 「전체」 하나로 뭉쳤다.
- 하위 조립 → 그 안의 부품들이 한 바디였다.
- 이름 없는 부품이 **하나라도** 있으면 → 조립 전체가 「전체」 하나였다.
- 같은 이름(볼트 4개) → 바디 이름이 겹쳐, 이름으로는 마지막 하나만 골랐다.
- 솔리드와 서피스가 한 부품에 → 서피스를 말없이 버렸다.
- 입체를 닫힌 셸로 낸 STEP → 부피 0 의 셸 모델이 됐다.
- 선 · 축뿐인 부품 → 부피 0 · 넓이 0 의 가짜 바디가 섰다.
- 한글 이름이 CP949 원문 → 이름이 깨졌다(UTF-8 원문 · `\\X2\\` 는 멀쩡하다).

여기서는 트리 **끝까지** 내려가 솔리드 하나 · 시트(셸) 하나가 바디 하나다. 이름은 그 부품의
이름이고, 비면 순번, 한 부품에서 여럿 나오거나 이름이 겹치면 `-2` 를 붙인다. 바디가 하나면
이름표를 붙이지 않는다 — 그려 만든 단품처럼 「전체」 다.

**옛 레시피는 옛 규칙 그대로다**(`evaluate.py`) — 바디 이름이 바뀌면 이미 건 해석 조건이
끊긴다.
"""

from __future__ import annotations

import copy
import tempfile
from dataclasses import dataclass
from pathlib import Path

from build123d import Compound, Location, Part, Shape, Solid, import_step
from OCP.BRep import BRep_Tool
from OCP.ShapeFix import ShapeFix_Solid
from OCP.TopoDS import TopoDS


@dataclass
class Body:
    name: str
    shape: Shape
    sheet: bool


def read(path: Path) -> Shape:
    """STEP 을 읽는다 — 이름이 **CP949 원문**이면 표준 이스케이프(`\\X2\\`)로 바꿔 읽는다.

    OCC 는 원문 바이트를 UTF-8 로 본다. 한글 윈도의 CAD 가 쓴 CP949 원문은 UTF-8 이 아니라
    「블록」 이 `º` 로 깨졌다(실측) — 깨진 이름끼리는 겹치기도 한다. 둘 다 아니면 Latin-1 이다.
    """
    data = path.read_bytes()
    if data.isascii():
        return import_step(path)
    try:
        data.decode("utf-8")
        return import_step(path)
    except UnicodeDecodeError:
        pass
    try:
        text = data.decode("cp949")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    with tempfile.TemporaryDirectory() as folder:
        escaped = Path(folder) / "escaped.step"
        escaped.write_bytes(_escaped(text).encode("ascii"))
        return import_step(escaped)


def _escaped(text: str) -> str:
    """아스키 밖의 글자를 STEP 의 `\\X2\\…\\X0\\`(그 밖은 `\\X4\\`)로. 그런 글자는 문자열
    안에만 있다 — 문자열 안에서는 이 이스케이프가 표준이다(ISO 10303-21)."""
    out: list[str] = []
    for one in text:
        code = ord(one)
        if code < 0x80:
            out.append(one)
        elif code <= 0xFFFF:
            out.append(f"\\X2\\{code:04X}\\X0\\")
        else:
            out.append(f"\\X4\\{code:08X}\\X0\\")
    return "".join(out)


def bodies(shape: Shape, notes: list[str]) -> list[Body]:
    """트리 끝의 솔리드 · 시트마다 한 바디. 바디가 아닌 것(선 · 점)은 빼고 `notes` 에
    적는다."""
    leaves: list[tuple[str, Shape]] = []
    _walk(shape, Location(), leaves)
    found: list[tuple[str, list[tuple[Shape, bool]]]] = []
    skipped: list[str] = []
    shelled = 0
    unsound: list[str] = []
    for label, leaf in leaves:
        pieces, closed = _pieces(leaf)
        shelled += closed
        if pieces:
            found.append((label, pieces))
        else:
            skipped.append(label or "(이름 없음)")
    out: list[Body] = []
    for label, pieces in found:
        for number, (piece, sheet) in enumerate(pieces, start=1):
            base = label or f"body_{len(out) + 1}"
            out.append(Body(base if len(pieces) == 1 else f"{base}-{number}", piece, sheet))
    _unique(out)
    for one in out:
        if not one.sheet and not one.shape.is_valid:
            unsound.append(one.name)
    if skipped:
        notes.append(
            f"STEP 에서 선 · 점뿐인 부품 {len(skipped)}개({_few(skipped)})는 바디가 아니라 "
            "뺐습니다."
        )
    if shelled:
        notes.append(f"STEP 의 닫힌 셸 {shelled}개를 솔리드로 바꿔 읽었습니다.")
    if unsound:
        notes.append(
            f"형상 검사를 통과하지 못한 바디가 있습니다({_few(unsound)}). 그대로 가져왔지만 "
            "구멍 · 필렛 같은 편집이나 메시에서 실패할 수 있습니다 — 원본 CAD 에서 고쳐 다시 "
            "내보내면 가장 확실합니다."
        )
    return out


def assembled(found: list[Body]) -> Shape:
    """바디들을 레시피가 쓰는 꼴로 — 여럿이면 바디마다 이름표 붙은 자식, 하나면 이름표 없이."""
    if len(found) == 1:
        only = found[0]
        if only.sheet:
            return Compound(only.shape.wrapped)
        return Part(children=[copy.copy(only.shape)])
    children = []
    for one in found:
        child = copy.copy(one.shape)
        child.label = one.name
        children.append(child)
    if any(not one.sheet for one in found):
        return Part(children=children)
    return Compound(children=children)


def _walk(node: Shape, above: Location, out: list[tuple[str, Shape]]) -> None:
    """트리 끝까지 — **위쪽 자리를 곱해 가며.** build123d 는 하위 조립의 자리를 그 조립에만
    두고 자식은 조립 안 좌표로 둔다. 자식을 그대로 꺼내면 하위 조립을 옮긴 만큼 어긋난다
    (실측: X 100 에 놓인 하위 조립의 부품이 0 에 나왔다)."""
    if node.wrapped is None or node.wrapped.IsNull():
        return
    kids = list(getattr(node, "children", ()) or ())
    if not kids:
        out.append((str(getattr(node, "label", "") or ""), node.moved(above)))
        return
    here = above * node.location
    for kid in kids:
        _walk(kid, here, out)


def _pieces(leaf: Shape) -> tuple[list[tuple[Shape, bool]], int]:
    """부품 하나에서 나오는 바디들 — (형상, 시트인가), 그리고 솔리드로 바꾼 닫힌 셸 수."""
    solids = list(leaf.solids())
    taken = {face for solid in solids for face in solid.faces()}
    pieces: list[tuple[Shape, bool]] = [(_sound(one), False) for one in solids]
    closed = 0
    in_shells: set[Shape] = set()
    for shell in leaf.shells():
        faces = shell.faces()
        if any(face in taken for face in faces):
            continue
        in_shells.update(faces)
        made = _solid_from(shell) if BRep_Tool.IsClosed_s(shell.wrapped) else None
        if made is not None:
            pieces.append((made, False))
            closed += 1
        else:
            pieces.append((shell, True))
    loose = [face for face in leaf.faces() if face not in taken and face not in in_shells]
    if loose:
        pieces.append((Compound(loose), True))
    return pieces, closed


def _solid_from(shell: Shape) -> Solid | None:
    """닫힌 셸 → 솔리드. 안 되면(부피가 안 서면) None — 시트로 남긴다."""
    try:
        made = Solid(ShapeFix_Solid().SolidFromShell(TopoDS.Shell_s(shell.wrapped)))
    except Exception:
        return None
    return made if made.volume > 0 else None


def _sound(solid: Solid) -> Solid:
    """뒤집힌 솔리드(부피가 음수)를 바로 세우고, 검사에 걸리면 한 번 고쳐 본다."""
    if solid.volume < 0:
        solid = Solid(solid.wrapped.Reversed())
    if not solid.is_valid:
        try:
            fixed = solid.fix()
        except Exception:
            return solid
        if isinstance(fixed, Solid) and fixed.volume > 0:
            return fixed
    return solid


def _unique(found: list[Body]) -> None:
    """이름이 겹치면 뒤의 것에 `-2`, `-3` … — 이름은 해석 조건이 바디를 고르는 손잡이다."""
    taken: set[str] = set()
    for one in found:
        name, number = one.name, 2
        while name in taken:
            name = f"{one.name}-{number}"
            number += 1
        one.name = name
        taken.add(name)


def _few(names: list[str]) -> str:
    return ", ".join(names[:5]) + (" …" if len(names) > 5 else "")
