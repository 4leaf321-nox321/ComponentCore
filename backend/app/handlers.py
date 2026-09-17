"""작업 종류 등록 — **조립 지점이다.** 서버(main.py)와 워커(worker.py)가 똑같이 부른다."""

from __future__ import annotations

from app.modules.cad import services as cad_services
from app.modules.jobs import registry
from app.modules.works import services as works_services


def register_all() -> None:
    registry.register(cad_services.JOB_KIND, cad_services.run_job)
    registry.register(works_services.JIG_JOB_KIND, works_services.run_jig_job)
