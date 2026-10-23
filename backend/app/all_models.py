"""모든 ORM 모델을 한 곳에서 import 한다.

Alembic autogenerate 는 Base.metadata 에 등록된 것만 본다. 여기에 한 줄을 더하지 않으면
**기존 표를 지우는** 마이그레이션이 생성된다. `tests/architecture` 가 검사한다.
"""

from __future__ import annotations

from app.database import Base
from app.modules.accounts.models import User
from app.modules.audit.models import AccessLog, AuditEntry, RequestTiming
from app.modules.auth.models import PersonalAccessToken, RefreshToken, SsoUsedJti
from app.modules.bundles.models import BundleRun, BundleUndoEntry
from app.modules.datasources.models import DataSource, DataSourceRun
from app.modules.doe.models import DoePoint, DoeStudy
from app.modules.files.models import Attachment, AttachmentTicket
from app.modules.jigs.models import Jig, JigVersion
from app.modules.jobs.models import Artifact, Job, WorkerBeat
from app.modules.materials.models import CatalogMaterial
from app.modules.metrics.models import (
    HomeMetric,
    MetricAlert,
    MetricAlertEvent,
    MetricDef,
    MetricRun,
    MetricValue,
)
from app.modules.notifications.models import Notification
from app.modules.objects.models import (
    ObjectAlias,
    ObjectInstance,
    ObjectLink,
    ObjectRef,
    ObjectRelation,
    ObjectRelationTombstone,
    ObjectWatch,
    ObjectYear,
    SavedView,
    SearchMiss,
)
from app.modules.ontology.models import (
    NavGroup,
    ObjectInterface,
    ObjectType,
    OntologySnapshot,
    PropertyDef,
    RelationType,
)
from app.modules.parts.models import Part, PartVersion
from app.modules.review.models import ReviewDecision
from app.modules.server.models import ServerSetting
from app.modules.specimens.models import SpecimenPreset
from app.modules.tagging.models import TagType
from app.modules.tasks.models import Job as Task
from app.modules.tasks.models import JobFile as TaskFile
from app.modules.tasks.models import WorkerHeartbeat
from app.modules.templates.models import RecipeTemplate
from app.modules.voc.models import VocAttachment, VocEvent, VocItem
from app.modules.webhooks.models import Webhook, WebhookDelivery
from app.modules.works.models import Work, WorkVersion
from app.modules.workspaces.models import Workspace, WorkspaceMember

__all__ = [
    "AccessLog",
    "Artifact",
    "Attachment",
    "AttachmentTicket",
    "AuditEntry",
    "Base",
    "BundleRun",
    "BundleUndoEntry",
    "CatalogMaterial",
    "DataSource",
    "DataSourceRun",
    "DoePoint",
    "DoeStudy",
    "HomeMetric",
    "Jig",
    "JigVersion",
    "Job",
    "MetricAlert",
    "MetricAlertEvent",
    "MetricDef",
    "MetricRun",
    "MetricValue",
    "NavGroup",
    "Notification",
    "ObjectAlias",
    "ObjectInstance",
    "ObjectInterface",
    "ObjectLink",
    "ObjectRef",
    "ObjectRelation",
    "ObjectRelationTombstone",
    "ObjectType",
    "ObjectWatch",
    "ObjectYear",
    "OntologySnapshot",
    "Part",
    "PartVersion",
    "PersonalAccessToken",
    "PropertyDef",
    "RecipeTemplate",
    "RefreshToken",
    "RelationType",
    "RequestTiming",
    "ReviewDecision",
    "SavedView",
    "SearchMiss",
    "ServerSetting",
    "SpecimenPreset",
    "SsoUsedJti",
    "TagType",
    "Task",
    "TaskFile",
    "User",
    "VocAttachment",
    "VocEvent",
    "VocItem",
    "Webhook",
    "WebhookDelivery",
    "Work",
    "WorkVersion",
    "WorkerBeat",
    "WorkerHeartbeat",
    "Workspace",
    "WorkspaceMember",
]
