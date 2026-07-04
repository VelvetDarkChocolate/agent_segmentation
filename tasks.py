import time
from celery_app import celery_app


@celery_app.task(bind=True)
def segmentation_task(
    self,
    case_id: str,
    filenames: list[str],
    model_name: str = "Seg-Model v2.0",
    threshold: float = 0.5,
):
    total = max(len(filenames), 1)

    for index, filename in enumerate(filenames, start=1):
        progress = int(index / total * 80)
        self.update_state(
            state="PROGRESS",
            meta={
                "progress": progress,
                "message": f"正在处理 {filename}",
            },
        )
        time.sleep(1)

    self.update_state(
        state="PROGRESS",
        meta={
            "progress": 90,
            "message": "正在生成量化指标与质控结果",
        },
    )
    time.sleep(1)

    return {
        "case_id": case_id,
        "model_name": model_name,
        "threshold": threshold,
        "status": "completed",
        "progress": 100,
        "preview": {
            "slice_index": 128,
            "total_slices": 256,
            "mode": "demo_overlay",
            "message": "Demo 分割已完成，当前预览为模拟叠加图",
        },
        "metrics": {
            "dice": 0.932,
            "iou": 0.878,
            "latency_seconds": 12.6,
        },
        "organs": [
            {"name": "肝脏", "volume_cm3": 1423.6, "ratio": "-", "max_diameter_cm": "-"},
            {"name": "肿瘤", "volume_cm3": 38.7, "ratio": "2.72%", "max_diameter_cm": 4.32},
            {"name": "血管", "volume_cm3": 96.4, "ratio": "6.78%", "max_diameter_cm": "-"},
            {"name": "胆囊", "volume_cm3": 22.1, "ratio": "1.55%", "max_diameter_cm": "-"},
        ],
        "review": {
            "ai_status": "AI初筛完成",
            "human_status": "待人工复核",
            "quality": "通过",
        },
    }
