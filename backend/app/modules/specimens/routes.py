"""시험 규격 라우터 — 목록 · 시편 미리 보기 · 내 작업 만들기는 로그인한 누구나, 사내 규격의
추가 · 수정 · 삭제는 시스템 관리자만."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.specimens import services
from app.modules.specimens.schemas import (
    PresetIn,
    PresetOut,
    ProductSourceRequest,
    ProductTestRequest,
    SpecimenBuildOut,
    SpecimenRequest,
    SpecimenWorkRequest,
)
from app.modules.works import services as works
from app.modules.works.schemas import WorkOut
from app.shared.auth import current_user, require_system_admin

router = APIRouter(prefix="/specimens", tags=["specimens"])


@router.get("/presets", response_model=list[PresetOut])
def list_presets(
    test: str = Query(default="", max_length=20),
    _: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[PresetOut]:
    """시험 규격 — 공개 규격(ASTM · ISO, 코드)과 사내 규격(DB)을 한 목록으로. `test` 로 시험
    종류(`bending` …)를 거른다. 규격서와 대조하기 전의 값은 `preset.verified=false`."""
    return services.list_presets(db, test)


@router.get("/presets/{preset_id}", response_model=PresetOut)
def get_preset(
    preset_id: str, _: User = Depends(current_user), db: Session = Depends(get_db)
) -> PresetOut:
    return services.find(db, preset_id)[1]


@router.post("/presets", response_model=PresetOut, status_code=201)
def create_preset(
    payload: PresetIn,
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> PresetOut:
    """**사내 규격**을 더한다 — 시스템 관리자만. 공개 규격과 같은 모양이고, 저장 전에 값 검사와
    실제로 그려 보기를 지난다(틀리면 400 과 `details.problems`)."""
    row = services.create_preset(db, user, payload.preset)
    return services.find(db, str(row.id))[1]


@router.put("/presets/{preset_id}", response_model=PresetOut)
def update_preset(
    preset_id: str,
    payload: PresetIn,
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> PresetOut:
    """사내 규격을 고친다 — 시스템 관리자만. 공개 규격은 고칠 수 없다(복사해 사내 규격으로)."""
    row = services.update_preset(db, user, preset_id, payload.preset)
    return services.find(db, str(row.id))[1]


@router.delete("/presets/{preset_id}", status_code=204)
def delete_preset(
    preset_id: str,
    _: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> None:
    """사내 규격을 지운다 — 이 규격으로 이미 만든 작업 · 지그는 그때의 값 그대로다."""
    services.delete_preset(db, preset_id)


@router.post("/build", response_model=SpecimenBuildOut)
def build(
    payload: SpecimenRequest, _: User = Depends(current_user), db: Session = Depends(get_db)
) -> SpecimenBuildOut:
    """시편(과 시험 지그 · 해석 조건)을 그려 본다 — 저장하지 않는다. 화면은 이 레시피를
    `/cad/recipe/mesh` 로 미리 보인다."""
    return services.build(db, payload)


@router.post("/works", response_model=WorkOut, status_code=201)
def create_work(
    payload: SpecimenWorkRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> WorkOut:
    """시험 규격으로 **내 작업**을 만든다 — 시편 치수가 레시피 변수라 바로 DOE 로 훑고, 해석
    조건이 함께 붙어 그대로 내보낸다."""
    return works.work_out(db, services.create_work(db, user, payload))


@router.post("/product-tests", response_model=WorkOut, status_code=201)
def apply_product_test(
    payload: ProductTestRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> WorkOut:
    """**제품에 시험 규격을 건다** — 정하중 · 손잡이·벽걸이 · 적층 압축 · 비틀림 · 정현파
    진동 · 고유진동수. 제품 레시피를 그대로 쓴 새 내 작업에 시험 변수 · 하중 자리 · 구속 ·
    하중 · 해석 설정을 붙인다. 제품의 물성 · 접촉 · 파트별 설정은 그대로 가져온다. 자리는
    기본이 아랫면 받침 · 윗면 하중이고, `faces` 로 3D 에서 고른 면을 준다."""
    return works.work_out(db, services.apply_product_test(db, user, payload))


@router.post("/product-mesh")
def product_mesh(
    payload: ProductSourceRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """제품의 면 · 엣지 메시와 요약 — 「제품에 적용」 이 3D 에서 고정 면 · 누를 면을
    고르게. 내 부품 작업은 주인 · 관리자만, 공용 부품은 누구나."""
    return services.product_mesh(db, user, payload)
