from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import TaskRecord
from backend.repositories.json_utils import dumps, loads


def serialize_task(task: TaskRecord) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "celery_task_id": task.celery_task_id,
        "case_id": task.case_id,
        "status": task.status,
        "progress": task.progress,
        "message": task.message,
        "result": loads(task.result_json, {}),
        "error": task.error,
        "created_at": task.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": task.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
    }


def create_task(session: Session, *, task_id: str, case_id: str, message: str = "") -> dict[str, Any]:
    task = TaskRecord(task_id=task_id, case_id=case_id, status="queued", progress=0, message=message)
    session.add(task)
    session.flush()
    return serialize_task(task)


def get_task(session: Session, task_id: str) -> TaskRecord | None:
    return session.get(TaskRecord, task_id)


def get_task_by_celery_id(session: Session, celery_task_id: str) -> TaskRecord | None:
    stmt = select(TaskRecord).where(TaskRecord.celery_task_id == celery_task_id)
    return session.scalars(stmt).first()


def attach_celery_id(session: Session, task_id: str, celery_task_id: str) -> dict[str, Any] | None:
    task = session.get(TaskRecord, task_id)
    if not task:
        return None
    task.celery_task_id = celery_task_id
    task.updated_at = datetime.utcnow()
    session.flush()
    return serialize_task(task)


def update_task(
    session: Session,
    task_id: str,
    *,
    status: str | None = None,
    progress: int | None = None,
    message: str | None = None,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any] | None:
    task = session.get(TaskRecord, task_id)
    if not task:
        return None
    if status is not None:
        task.status = status
    if progress is not None:
        task.progress = progress
    if message is not None:
        task.message = message
    if result is not None:
        task.result_json = dumps(result)
    if error is not None:
        task.error = error
    task.updated_at = datetime.utcnow()
    session.flush()
    return serialize_task(task)

