from typing import Any, Dict, List

import requests

from agent.authority_retriever import authority_status, search_authority_pdf_chunks
from agent.prompts import LOCAL_PDF_AUTHORITY_SEGMENTATION_PROMPT, FORBIDDEN_TERMS, SAFETY_STATEMENT
from agent.segmentation_context import (
    build_authority_pdf_retrieval_query,
    build_segmentation_facts,
    format_model_facts,
)


def build_grounded_prompt_context(
    segmentation_facts: Dict[str, Any],
    citations: List[Dict[str, Any]],
    retrieval_query: str,
) -> str:
    evidence_lines = []
    if citations:
        for citation in citations:
            evidence_lines.append(
                "\n".join(
                    [
                        f"source_id: {citation['source_id']}",
                        f"title: {citation['title']}",
                        f"publisher: {citation['publisher']}",
                        f"source_url: {citation['source_url']}",
                        f"pdf_url: {citation['pdf_url']}",
                        f"pages: {citation['page_start']}-{citation['page_end']}",
                        f"section: {citation.get('section_title', 'General')}",
                        f"preview: {citation['preview']}",
                    ]
                )
            )
    else:
        evidence_lines.append("当前本地权威 PDF 知识库证据不足（权威知识库证据不足），以下仅基于模型输出事实进行科研描述。")

    return f"""
[MODEL_FACTS]
{format_model_facts(segmentation_facts)}

[AUTHORITY_EVIDENCE]
{chr(10).join(evidence_lines)}

[RETRIEVAL_QUERY]
{retrieval_query}

[REASONING_RULES]
- 区分模型事实、权威依据、推理性分析。
- 不把模型预测当作真实标注。
- 不把单切片面积占比解释为体积。
- 没有 GT 时不能计算 Dice/HD95。
- 小器官边界误差对 percentage 影响更明显。
- 输出复核建议，不输出诊断结论。

[OUTPUT_REQUIREMENTS]
- 中文。
- 科研汇报格式。
- 必须列出 PDF citation、页码和 source_url。
- 必须包含安全声明。
- 必须包含局限性。
- 禁止临床诊断。
"""


def sanitize_answer(answer: str) -> str:
    sanitized = answer
    for term in FORBIDDEN_TERMS:
        sanitized = sanitized.replace(term, "不作临床判断")
    if SAFETY_STATEMENT not in sanitized:
        sanitized += f"\n\n{SAFETY_STATEMENT}"
    return sanitized


def fallback_authority_report(segmentation_facts: Dict[str, Any], citations: List[Dict[str, Any]]) -> str:
    lines = [
        "## 基于本地权威 PDF 知识库的科研辅助分析",
        "",
        "### 1. 模型输出事实",
        format_model_facts(segmentation_facts),
        "",
        "### 2. PDF 权威文档依据",
    ]
    if citations:
        for citation in citations:
            lines.append(
                f"- [{citation['source_id']}] {citation['title']}, {citation['publisher']}, "
                f"pages {citation['page_start']}-{citation['page_end']}, {citation['source_url']}"
            )
    else:
        lines.append("- 当前本地权威 PDF 知识库证据不足（权威知识库证据不足），以下仅基于模型输出事实进行科研描述。")

    lines.extend(
        [
            "",
            "### 3. 器官分布与分割结果解释",
            "上述 pixel_count 和 percentage 来自 /predict 的模型预测输出，可用于单切片层面的科研辅助描述。percentage 表示该切片中预测区域的像素占比，不应解释为三维体积或临床范围。",
            "",
            "### 4. 分割质量与人工复核建议",
            "建议优先复核面积占比较低、小器官、边界细长或邻近高对比结构的预测区域。若需要 Dice、IoU 或 HD95，必须提供 ground truth 标注后再计算。",
            "",
            "### 5. 局限性",
            "- 单切片不能代表整体体积。",
            "- 没有 GT 不能计算 Dice/HD95。",
            "- 模型预测不能替代医生标注。",
            "",
            "### 6. 科研汇报版总结",
            "本次分割结果可作为 MMRSG-UNet 在腹部多器官单切片分割任务中的模型输出展示，用于描述器官预测区域、像素级面积占比和后续人工复核重点。",
            "",
            SAFETY_STATEMENT,
        ]
    )
    return "\n".join(lines)


def call_llm(api_key: str, base_url: str, model_name: str, message: str, context: str) -> str:
    response = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model_name,
            "messages": [
                {"role": "system", "content": LOCAL_PDF_AUTHORITY_SEGMENTATION_PROMPT},
                {"role": "user", "content": f"{context}\n\n用户问题：{message}"},
            ],
            "temperature": 0.2,
            "stream": False,
        },
        timeout=45,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def analyze_segmentation_with_authority(
    message: str,
    segmentation_result: Dict[str, Any],
    top_k: int,
    min_authority_level: int,
    authority_only: bool,
    api_key: str = "",
    base_url: str = "https://api.deepseek.com",
    model_name: str = "deepseek-v4-flash",
    ) -> Dict[str, Any]:
    segmentation_facts = build_segmentation_facts(segmentation_result)
    retrieval_query = build_authority_pdf_retrieval_query(message, segmentation_facts)
    citations = search_authority_pdf_chunks(retrieval_query, top_k=top_k, min_authority_level=min_authority_level)
    context = build_grounded_prompt_context(segmentation_facts, citations, retrieval_query)

    if api_key and citations:
        try:
            answer = call_llm(api_key, base_url, model_name, message, context)
        except Exception:
            answer = fallback_authority_report(segmentation_facts, citations)
    else:
        answer = fallback_authority_report(segmentation_facts, citations)

    answer = sanitize_answer(answer)
    return {
        "answer": answer,
        "tools_used": [
            "build_segmentation_facts",
            "build_authority_pdf_retrieval_query",
            "search_authority_pdf_chunks",
            "generate_local_pdf_authority_report",
        ],
        "citations": citations,
        "segmentation_facts": segmentation_facts,
        "authority_context": {
            "retrieval_query": retrieval_query,
            "min_authority_level": min_authority_level,
            "authority_only": authority_only,
            "sources_used": sorted({citation["source_id"] for citation in citations}),
        },
        "report": {"title": "Local-PDF Authority Segmentation Research Report", "body": answer},
    }


__all__ = ["analyze_segmentation_with_authority", "authority_status"]
