import uuid
from pathlib import Path
from typing import Any

from backend.core.database import session_scope
from backend.repositories import case_repo, report_repo, task_repo
from backend.repositories.json_utils import loads
from backend.services.inference_service import inference_service
from backend.services.storage_service import object_store


def create_segmentation_record(case_id: str) -> dict[str, Any]:
    task_id = f"SEG-{uuid.uuid4().hex[:12]}"
    with session_scope() as session:
        case = case_repo.get_case(session, case_id)
        if not case:
            raise KeyError("病例不存在，请先上传数据")
        task = task_repo.create_task(session, task_id=task_id, case_id=case_id, message="任务已创建")
        case_repo.update_case_status(session, case_id, "queued", task_id=task_id)
        return task


def case_exists(case_id: str) -> bool:
    with session_scope() as session:
        return case_repo.get_case(session, case_id) is not None


def attach_celery_task(task_id: str, celery_task_id: str) -> None:
    with session_scope() as session:
        task_repo.attach_celery_id(session, task_id, celery_task_id)


def get_case_files(case_id: str) -> list[tuple[str, bytes]]:
    with session_scope() as session:
        case = case_repo.get_case(session, case_id)
        if not case:
            raise KeyError("病例不存在，请先上传数据")
        filenames = loads(case.filenames_json, [])
        object_keys = loads(case.object_keys_json, [])

    files = []
    for filename, object_key in zip(filenames, object_keys):
        files.append((filename, object_store.path_for(object_key).read_bytes()))
    return files


def mark_task_progress(task_id: str, status: str, progress: int, message: str) -> None:
    with session_scope() as session:
        task = task_repo.update_task(session, task_id, status=status, progress=progress, message=message)
        if task:
            case_status = "running" if status == "running" else status
            case_repo.update_case_status(session, task["case_id"], case_status, task_id=task_id)


def legacy_organs_from_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    aggregate: dict[str, int] = {}
    for result in results:
        for metric in result.get("metrics", []):
            organ = metric.get("organ", "unknown")
            aggregate[organ] = aggregate.get(organ, 0) + int(metric.get("pixel_count", 0))
    total = sum(aggregate.values()) or 1
    return [
        {
            "name": organ,
            "volume_cm3": "-",
            "ratio": f"{(pixels / total) * 100:.2f}%",
            "max_diameter_cm": "-",
            "pixel_count": pixels,
        }
        for organ, pixels in sorted(aggregate.items(), key=lambda item: item[0])
    ]


def complete_segmentation_task(task_id: str, result: dict[str, Any]) -> dict[str, Any]:
    case_id = result.get("case_id")
    report_id = f"REPORT-{task_id}"
    report = {
        **result,
        "status": "completed",
        "progress": 100,
        "preview": {
            "mode": "real_overlay",
            "message": "真实模型分割已完成，mask_url/overlay_url 指向对象存储文件",
        },
        "metrics": {
            "latency_seconds": result.get("latency_seconds"),
            "dice": None,
            "iou": None,
            "note": "未提供 ground truth，不能计算 Dice/IoU/HD95。",
        },
        "organs": legacy_organs_from_results(result.get("results", [])),
        "review": {
            "ai_status": "AI初筛完成",
            "human_status": "待人工复核",
            "quality": "待复核",
        },
    }
    with session_scope() as session:
        task_repo.update_task(session, task_id, status="completed", progress=100, message="任务完成", result=report)
        if case_id:
            case_repo.update_case_status(session, case_id, "completed", task_id=task_id)
            return report_repo.save_report(
                session,
                report_id=report_id,
                case_id=case_id,
                task_id=task_id,
                model_name=result.get("model_name", ""),
                result=report,
            )
    return report


def fail_segmentation_task(task_id: str, error: str) -> None:
    with session_scope() as session:
        task = task_repo.update_task(
            session,
            task_id,
            status="failed",
            progress=0,
            message="任务失败",
            error=error,
        )
        if task:
            case_repo.update_case_status(session, task["case_id"], "failed", task_id=task_id)


def run_persisted_segmentation_task(
    *,
    task_id: str,
    case_id: str,
    model_name: str,
    threshold: float,
    update_progress: Any | None = None,
) -> dict[str, Any]:
    def progress(progress_value: int, message: str) -> None:
        mark_task_progress(task_id, "running", progress_value, message)
        if update_progress:
            update_progress(progress_value, message)

    mark_task_progress(task_id, "running", 5, "任务开始")
    files = get_case_files(case_id)
    result = inference_service.run(
        files=files,
        alpha=threshold,
        model_name=model_name,
        case_id=case_id,
        task_id=task_id,
        include_base64=False,
        persist_outputs=True,
        progress_callback=progress,
    )
    complete_segmentation_task(task_id, result)
    return result


def get_task_status_payload(task_id: str) -> dict[str, Any] | None:
    with session_scope() as session:
        task = task_repo.get_task(session, task_id)
        if not task:
            return None
        return task_repo.serialize_task(task)


def list_reports() -> list[dict[str, Any]]:
    with session_scope() as session:
        return report_repo.list_reports(session)
