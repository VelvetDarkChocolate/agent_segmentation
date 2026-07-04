from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import ReportRecord
from backend.repositories.json_utils import dumps, loads


def serialize_report(report: ReportRecord) -> dict[str, Any]:
    result = loads(report.result_json, {})
    legacy = {
        "report_id": report.report_id,
        "case_id": report.case_id,
        "task_id": report.task_id,
        "model_name": report.model_name,
        "status": report.status,
        "created_at": report.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "result": result,
    }
    if isinstance(result, dict):
        legacy.update(result)
    return legacy


def save_report(
    session: Session,
    *,
    report_id: str,
    case_id: str,
    task_id: str | None,
    model_name: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    report = ReportRecord(
        report_id=report_id,
        case_id=case_id,
        task_id=task_id,
        model_name=model_name,
        status=result.get("status", "completed"),
        result_json=dumps(result),
    )
    report = session.merge(report)
    session.flush()
    return serialize_report(report)


def list_reports(session: Session) -> list[dict[str, Any]]:
    reports = session.scalars(select(ReportRecord).order_by(ReportRecord.created_at.desc())).all()
    return [serialize_report(report) for report in reports]
