from celery_app import celery_app
from backend.services.segmentation_service import fail_segmentation_task, run_persisted_segmentation_task


@celery_app.task(bind=True)
def segmentation_task(
    self,
    task_id: str | None = None,
    case_id: str | None = None,
    filenames: list[str] | None = None,
    model_name: str = "Seg-Model v2.0",
    threshold: float = 0.5,
):
    def update_progress(progress: int, message: str) -> None:
        self.update_state(state="PROGRESS", meta={"progress": progress, "message": message})

    try:
        if not task_id:
            raise ValueError(
                "旧版 Celery 消息缺少 task_id，请重新通过 /api/v1/segmentations 创建持久化任务。"
            )
        if not case_id:
            raise ValueError("任务缺少 case_id")
        return run_persisted_segmentation_task(
            task_id=task_id,
            case_id=case_id,
            model_name=model_name,
            threshold=threshold,
            update_progress=update_progress,
        )
    except Exception as exc:
        fail_segmentation_task(task_id, str(exc))
        raise
