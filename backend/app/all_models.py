"""모든 ORM 모델을 한 곳에서 import 한다.

Alembic autogenerate 는 Base.metadata 에 등록된 것만 본다. 여기에 한 줄을 더하지 않으면
**기존 표를 지우는** 마이그레이션이 생성된다. `tests/architecture` 가 검사한다.
"""

from __future__ import annotations

from app.database import Base
from app.modules.accounts.models import User
from app.modules.audit.models import AccessLog
from app.modules.auth.models import PersonalAccessToken, RefreshToken
from app.modules.cad.models import RecipeTemplate
from app.modules.jigs.models import Jig, JigVersion
from app.modules.jobs.models import Artifact, Job
from app.modules.parts.models import Part, PartVersion
from app.modules.works.models import Work, WorkVersion

__all__ = [
    "AccessLog",
    "Artifact",
    "Base",
    "Jig",
    "JigVersion",
    "Job",
    "Part",
    "PartVersion",
    "PersonalAccessToken",
    "RecipeTemplate",
    "RefreshToken",
    "User",
    "Work",
    "WorkVersion",
]
