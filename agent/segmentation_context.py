from typing import Any, Dict, List


ORGAN_QUERY_HINTS = {
    "主动脉": "主动脉 aorta abdominal imaging",
    "胆囊": "胆囊 gallbladder abdominal anatomy",
    "左肾": "肾 kidney retroperitoneum",
    "右肾": "肾 kidney retroperitoneum",
    "肝脏": "肝脏 liver anatomy abdominal CT",
    "胰腺": "胰腺 pancreas retroperitoneum",
    "脾脏": "脾脏 spleen anatomy",
    "胃": "胃 stomach anatomy",
}


def build_segmentation_facts(segmentation_result: Dict[str, Any]) -> Dict[str, Any]:
    results = segmentation_result.get("results")
    if results is None and segmentation_result.get("filename"):
        results = [segmentation_result]
    results = results or []

    slices = []
    organ_totals: Dict[str, Dict[str, Any]] = {}
    for index, item in enumerate(results):
        metrics = item.get("metrics", []) or []
        organs = []
        for metric in metrics:
            organ = metric.get("organ", "unknown")
            pixel_count = int(metric.get("pixel_count", 0) or 0)
            percentage_text = str(metric.get("percentage", "0")).replace("%", "")
            try:
                percentage = float(percentage_text)
            except ValueError:
                percentage = 0.0
            organs.append({"organ": organ, "pixel_count": pixel_count, "percentage": percentage})
            organ_totals.setdefault(organ, {"pixel_count": 0, "percentage": 0.0, "slices": 0})
            organ_totals[organ]["pixel_count"] += pixel_count
            organ_totals[organ]["percentage"] += percentage
            organ_totals[organ]["slices"] += 1
        slices.append({"index": index + 1, "filename": item.get("filename", f"slice-{index + 1}"), "organs": organs})

    total_percentage = round(sum(value["percentage"] for value in organ_totals.values()), 3)
    organ_stats = [
        {
            "organ": organ,
            "pixel_count": value["pixel_count"],
            "percentage": round(value["percentage"], 3),
            "slice_count": value["slices"],
        }
        for organ, value in organ_totals.items()
    ]
    top_organs = sorted(organ_stats, key=lambda item: item["percentage"], reverse=True)[:5]
    small_organs = [item for item in organ_stats if 0 < item["percentage"] < 1.0 or item["pixel_count"] < 300]
    possible_review_points = [
        "优先复核小器官、面积占比较低结构和边界细长区域。",
        "如果没有 ground truth，不能从该结果计算 Dice、IoU 或 HD95。",
        "单切片 percentage 只表示该二维切片上的模型预测像素占比。",
    ]
    return {
        "model_name": segmentation_result.get("model_name", "MMRSG-UNet epoch_241.pth"),
        "image_name": ", ".join(item["filename"] for item in slices) if slices else segmentation_result.get("filename", ""),
        "source_api": "/predict",
        "slice_count": len(slices),
        "slices": slices,
        "organ_count": len(organ_totals),
        "organs_detected": list(organ_totals.keys()),
        "organ_stats": organ_stats,
        "organ_totals": organ_totals,
        "total_area_percentage": total_percentage,
        "top_organs_by_area": top_organs,
        "small_organs": small_organs,
        "possible_review_points": possible_review_points,
        "limitations": [
            "single_slice_area_percentage_not_volume",
            "model_prediction_not_doctor_annotation",
            "ground_truth_required_for_dice_hd95",
        ],
        "has_ground_truth": bool(segmentation_result.get("ground_truth")),
    }


def build_authority_pdf_retrieval_query(user_message: str, segmentation_facts: Dict[str, Any]) -> str:
    organs = list(segmentation_facts.get("organs_detected") or segmentation_facts.get("organ_totals", {}).keys())
    organ_hints = [ORGAN_QUERY_HINTS.get(organ, organ) for organ in organs]
    terms = [
        user_message,
        "腹部 CT 多器官分割 单切片 器官面积占比 pixel count percentage",
        "MMRSG-UNet medical image segmentation",
        "Dice IoU Jaccard HD95 Hausdorff surface distance ground truth",
        "manual review single slice limitation volume multi-organ segmentation benchmark evaluation",
        "人工复核 科研辅助分析 模型质控",
        *organ_hints,
    ]
    return " ".join(term for term in terms if term)


def build_authority_retrieval_query(user_message: str, segmentation_facts: Dict[str, Any]) -> str:
    return build_authority_pdf_retrieval_query(user_message, segmentation_facts)


def format_model_facts(segmentation_facts: Dict[str, Any]) -> str:
    lines = [
        f"source_api: {segmentation_facts.get('source_api')}",
        f"model_name: {segmentation_facts.get('model_name')}",
        f"slice_count: {segmentation_facts.get('slice_count')}",
        f"organ_count: {segmentation_facts.get('organ_count')}",
        f"total_area_percentage_sum: {segmentation_facts.get('total_area_percentage')}%",
        f"has_ground_truth: {segmentation_facts.get('has_ground_truth')}",
    ]
    for item in segmentation_facts.get("slices", []):
        lines.append(f"\nSlice {item['index']}: {item['filename']}")
        if not item["organs"]:
            lines.append("- no visible organ metrics returned by model")
        for organ in item["organs"]:
            lines.append(f"- {organ['organ']}: pixel_count={organ['pixel_count']}, percentage={organ['percentage']}%")
    return "\n".join(lines)
