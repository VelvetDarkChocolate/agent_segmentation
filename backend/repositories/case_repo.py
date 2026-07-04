from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import CaseRecord
from backend.repositories.json_utils import dumps, loads


STATUS_LABELS = {
    "uploaded": "已上传",
    "queued": "已排队",
    "running": "处理中",
    "completed": "已完成",
    "failed": "失败",
    "reviewed": "已复核",
}


def serialize_case(case: CaseRecord) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "modality": case.modality,
        "body_part": case.body_part,
        "file_count": case.file_count,
        "filenames": loads(case.filenames_json, []),
        "object_keys": loads(case.object_keys_json, []),
        "status": case.status,
        "status_label": STATUS_LABELS.get(case.status, case.status),
        "task_id": case.task_id,
        "created_at": case.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": case.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
    }


def create_case(
    session: Session,
    *,
    case_id: str,
    modality: str,
    body_part: str,
    filenames: list[str],
    object_keys: list[str],
) -> dict[str, Any]:
    case = CaseRecord(
        case_id=case_id,
        modality=modality,
        body_part=body_part,
        file_count=len(filenames),
        filenames_json=dumps(filenames),
        object_keys_json=dumps(object_keys),
        status="uploaded",
    )
    session.add(case)
    session.flush()
    return serialize_case(case)


def get_case(session: Session, case_id: str) -> CaseRecord | None:
    return session.get(CaseRecord, case_id)


def list_cases(session: Session) -> list[dict[str, Any]]:
    cases = session.scalars(select(CaseRecord).order_by(CaseRecord.created_at.desc())).all()
    return [serialize_case(case) for case in cases]


def update_case_status(
    session: Session,
    case_id: str,
    status: str,
    task_id: str | None = None,
) -> dict[str, Any] | None:
    case = session.get(CaseRecord, case_id)
    if not case:
        return None
    case.status = status
    if task_id is not None:
        case.task_id = task_id
    case.updated_at = datetime.utcnow()
    session.flush()
    return serialize_case(case)

