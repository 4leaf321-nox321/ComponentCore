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

**이름 규칙**(`names`, 2026-11-18): build123d 의 `import_step` 은 이름의 공백 · 점 · 괄호를 `_`
로 바꾼다(그쪽 뷰어가 그런 이름에서 죽어서) — `1번 판` 이 `1번_판` 이 됐다. 내보낼 때는 이제
이름이 그대로 나가므로(`export.write_step`) 다시 올리면 이름이 달라졌다. `original` 은 STEP 의
이름 그대로 읽는다(`_import_original`). 이미 가져온 레시피는 `legacy`(기본)라 그대로다.
"""

from __future__ import annotations

import copy
import tempfile
import unicodedata
from dataclasses import dataclass
from os import fsdecode
from pathlib import Path
from typing import Literal

from build123d import Compound, Location, Part, Shape, Solid, import_step
from build123d.importers import topods_lut
from build123d.topology import downcast
from OCP.BRep import BRep_Tool
from OCP.gp import gp_TrsfForm
from OCP.ShapeFix import ShapeFix_Solid
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TCollection import TCollection_AsciiString, TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_Label, TDF_LabelSequence
from OCP.TDocStd import TDocStd_Document
from OCP.TopoDS import TopoDS
from OCP.XCAFDoc import XCAFDoc_DocumentTool

#: 바디 이름 규칙 — `legacy` 는 build123d 그대로(공백 · 점 · 괄호 → `_`), `original` 은 STEP 의
#: 이름 그대로.
Names = Literal["legacy", "original"]


@dataclass
class Body:
    name: str
    shape: Shape
    sheet: bool


def read(path: Path, names: Names = "legacy") -> Shape:
    """STEP 을 읽는다 — 이름이 **CP949 원문**이면 표준 이스케이프(`\\X2\\`)로 바꿔 읽는다.

    OCC 는 원문 바이트를 UTF-8 로 본다. 한글 윈도의 CAD 가 쓴 CP949 원문은 UTF-8 이 아니라
    「블록」 이 `º` 로 깨졌다(실측) — 깨진 이름끼리는 겹치기도 한다. 둘 다 아니면 Latin-1 이다.
    """
    reader = _import_original if names == "original" else import_step
    data = path.read_bytes()
    if data.isascii():
        return reader(path)
    try:
        data.decode("utf-8")
        return reader(path)
    except UnicodeDecodeError:
        pass
    try:
        text = data.decode("cp949")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    with tempfile.TemporaryDirectory() as folder:
        escaped = Path(folder) / "escaped.step"
        escaped.write_bytes(_escaped(text).encode("ascii"))
        return reader(escaped)


def _import_original(path: Path) -> Shape:
    """build123d `import_step`(0.11.1)과 같은 트리 · 자리 — **이름만 STEP 그대로**.

    build123d 는 이름의 공백 · 점 · 괄호를 `_` 로 바꾸고, 그 함수 안의 함수라 바꿔 끼울 수
    없다. 그래서 같은 순서로 같은 것을 읽되 이름은 제어 문자만 뺀다. 색은 읽지 않는다 — 바디로
    가르면(`bodies`) 어차피 남지 않고, 쓰는 곳도 없다(읽는 값이 비싸다). build123d 를 올리면
    `test_core_step_names` 가 둘이 이름 말고는 같은지(바디 수 · 부피 · 자리) 본다."""
    if not path.exists():
        raise FileNotFoundError(path)
    doc = TDocStd_Document(TCollection_ExtendedString("XCAF"))
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    reader.ReadFile(fsdecode(path))
    reader.Transfer(doc)

    def name_of(label: TDF_Label) -> str:
        # 제어 문자를 빼고 **앞뒤 공백을 지운다** — 바디 이름은 해석 쪽이 `apply_to` ·
        # `body_settings` 와 견줘 짝짓는다(SimEngBay, 2026-11-18). 가운데 공백은 그대로.
        found = TDataStd_Name()
        name = ""
        if label.FindAttribute(TDataStd_Name.GetID_s(), found):
            name = TCollection_AsciiString(found.Get()).ToCString()
        return "".join(ch for ch in name if unicodedata.category(ch)[0] != "C").strip()

    def build(parent: TDF_Label | None) -> list[Shape]:
        labels = TDF_LabelSequence()
        if parent is None:
            shape_tool.GetFreeShapes(labels)
        else:
            shape_tool.GetComponents_s(parent, labels)
        out: list[Shape] = []
        for index in range(labels.Length()):
            here = labels.Value(index + 1)
            referred = here
            if shape_tool.IsReference_s(here):
                referred = TDF_Label()
                shape_tool.GetReferredShape_s(here, referred)
            made: Shape
            if shape_tool.IsAssembly_s(referred):
                made = Compound()
                made.children = build(referred)
            else:
                topo = downcast(shape_tool.GetShape_s(referred))
                made = topods_lut[type(topo)](topo)
            made.label = name_of(referred)
            made.move(Location(shape_tool.GetLocation_s(here)))
            out.append(made)
        return out

    root = Compound()
    root.children = build(None)
    # 맨 위가 하나면 감싼 Compound 를 벗긴다 — build123d 와 같게.
    return root.children[0] if len(root.children) == 1 else root


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


#: 읽어 가른 STEP — (경로, 고친 시각, 크기) 마다. 바디마다 노드로 가르면 노드 수만큼 읽게 되고,
#: 큰 조립 STEP 은 한 번에 몇 초다. 꺼낸 형상은 복사해서 쓴다(`single` · `assembled`).
_SPLIT_CACHE: dict[tuple[str, int, int, str], tuple[list[Body], list[str]]] = {}
_SPLIT_CACHE_SIZE = 4


def split(path: Path, names: Names = "legacy") -> tuple[list[Body], list[str]]:
    """STEP 을 읽어 바디로 가른 것과 파일에 대한 말(`bodies` 의 notes). 같은 파일이면 다시 읽지
    않는다 — 파일이 바뀌면(시각 · 크기) 다시 읽는다. 이름 규칙(`names`)마다 따로 둔다."""
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size, names)
    got = _SPLIT_CACHE.get(key)
    if got is None:
        notes: list[str] = []
        got = (bodies(read(path, names), notes), notes)
        if len(_SPLIT_CACHE) >= _SPLIT_CACHE_SIZE:
            _SPLIT_CACHE.pop(next(iter(_SPLIT_CACHE)))
        _SPLIT_CACHE[key] = got
    found, notes = got
    return list(found), list(notes)


def few(names: list[str]) -> str:
    return _few(names)


def single(body: Body) -> Shape:
    """바디 하나를 레시피가 쓰는 꼴로 — 제 이름을 든다(`group` 의 `names: "body"` 가 그것을
    쓴다)."""
    made: Shape = (
        Compound(body.shape.wrapped) if body.sheet else Part(children=[copy.copy(body.shape)])
    )
    made.label = body.name
    return made


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
        # **자리가 없으면 옮기지 않는다.** 빈 `Location()` 도 「항등 변환」 이라는 자리를
        # 붙이고, STEP 쓰기는 자리가 붙은 형상을 부품 하나로 싸 조립을 한 겹 더 만든다 —
        # 시트 하나짜리 셸 모델 STEP 이 「model 안의 model」 로 나갔다(SimEngBay 가 픽스처에서
        # 봄, 2026-11-16).
        label = str(getattr(node, "label", "") or "")
        out.append((label, node if _identity(above) else node.moved(above)))
        return
    here = node.location if _identity(above) else above * node.location
    for kid in kids:
        _walk(kid, here, out)


def _identity(where: Location) -> bool:
    """옮기지도 돌리지도 않는 자리인가 — 표식(`IsIdentity`)이 없어도 변환이 항등이면."""
    return bool(
        where.wrapped.IsIdentity()
        or where.wrapped.Transformation().Form() == gp_TrsfForm.gp_Identity
    )


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
