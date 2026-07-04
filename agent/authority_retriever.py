import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.authority_pdf_loader import (
    AUTHORITY_DIR,
    CHUNKS_PATH,
    REGISTRY_PATH,
    get_pdf_dir,
    load_source_registry,
    validate_local_pdfs,
)


MANIFEST_PATH = AUTHORITY_DIR / "manifest.json"

ORGAN_TERMS = {
    "肝脏": ["肝脏", "肝", "liver", "hepatic"],
    "脾脏": ["脾脏", "脾", "spleen", "splenic"],
    "胃": ["胃", "stomach", "gastric"],
    "胰腺": ["胰腺", "pancreas", "pancreatic"],
    "胆囊": ["胆囊", "gallbladder"],
    "肾": ["肾", "左肾", "右肾", "kidney", "renal"],
    "主动脉": ["主动脉", "aorta", "aortic"],
}
METRIC_TERMS = ["dice", "iou", "jaccard", "hd95", "hausdorff", "surface distance", "pixel_count", "percentage", "面积占比", "像素"]
TASK_TERMS = ["ct", "abdominal", "multi-organ", "segmentation", "benchmark", "evaluation", "single slice", "volume", "ground truth", "manual review", "腹部", "分割", "单切片", "人工复核"]


def load_authority_chunks(path: Path = CHUNKS_PATH) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    chunks = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    return chunks


def authority_status() -> Dict[str, Any]:
    registry = load_source_registry(REGISTRY_PATH)
    pdf_dir = get_pdf_dir()
    validation = validate_local_pdfs(registry, pdf_dir)
    chunks = load_authority_chunks()
    manifest = {}
    if MANIFEST_PATH.exists():
        try:
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}

    indexed_sources = manifest.get("indexed_sources", len({chunk.get("source_id") for chunk in chunks}))
    indexed_chunks = manifest.get("indexed_chunks", len(chunks))
    return {
        "registered_sources": len(registry.get("sources", [])),
        "available_pdfs": len(validation["available_pdfs"]),
        "missing_pdfs": validation["missing_pdfs"],
        "indexed_sources": indexed_sources,
        "indexed_chunks": indexed_chunks,
        "store_type": manifest.get("store_type", "fallback_json"),
        "manifest_path": str(MANIFEST_PATH),
        "pdf_dir": str(pdf_dir),
        "sources": [
            {
                "source_id": item["id"],
                "filename": item["filename"],
                "title": item["title"],
                "source_url": item["source_url"],
                "pdf_url": item["pdf_url"],
                "publisher": item["publisher"],
                "source_type": item["source_type"],
                "authority_level": item["authority_level"],
                "allowed_for_rag": item["allowed_for_rag"],
            }
            for item in registry.get("sources", [])
        ],
    }


def tokenize(text: str) -> List[str]:
    return re.findall(r"[A-Za-z0-9_\-]+|[\u4e00-\u9fff]", text.lower())


def keyword_score(query: str, chunk: Dict[str, Any]) -> float:
    query_tokens = Counter(tokenize(query))
    text = " ".join(
        [
            chunk.get("title", ""),
            chunk.get("section_title", ""),
            chunk.get("preview", ""),
            chunk.get("text", ""),
            " ".join(chunk.get("domain", [])),
            " ".join(chunk.get("organ_tags", [])),
            " ".join(chunk.get("metric_tags", [])),
            " ".join(chunk.get("task_tags", [])),
        ]
    )
    text_tokens = Counter(tokenize(text))
    if not query_tokens or not text_tokens:
        base = 0.0
    else:
        overlap = sum(min(count, text_tokens[token]) for token, count in query_tokens.items())
        base = overlap / math.sqrt(sum(query_tokens.values()) * sum(text_tokens.values()))

    lower_query = query.lower()
    lower_text = text.lower()
    organ_bonus = 0.0
    for terms in ORGAN_TERMS.values():
        if any(term.lower() in lower_query for term in terms) and any(term.lower() in lower_text for term in terms):
            organ_bonus += 0.18
    metric_bonus = sum(0.06 for term in METRIC_TERMS if term.lower() in lower_query and term.lower() in lower_text)
    task_bonus = sum(0.04 for term in TASK_TERMS if term.lower() in lower_query and term.lower() in lower_text)
    authority_bonus = 0.08 * int(chunk.get("authority_level", 0))
    return base + organ_bonus + metric_bonus + task_bonus + authority_bonus


def citation_from_chunk(chunk: Dict[str, Any], score: float) -> Dict[str, Any]:
    source_url = chunk.get("source_url") or chunk.get("url", "")
    return {
        "source_id": chunk["source_id"],
        "title": chunk["title"],
        "publisher": chunk["publisher"],
        "source_url": source_url,
        "url": source_url,
        "pdf_url": chunk.get("pdf_url", source_url),
        "page_start": chunk.get("page_start", 1),
        "page_end": chunk.get("page_end", chunk.get("page_start", 1)),
        "chunk_id": chunk["chunk_id"],
        "preview": chunk.get("preview") or chunk.get("text", "")[:360],
        "score": round(score, 4),
        "authority_level": chunk["authority_level"],
        "section_title": chunk.get("section_title", "General"),
        "source_type": chunk.get("source_type", ""),
    }


def search_authority_pdf_chunks(
    query: str,
    top_k: int = 8,
    min_authority_level: int = 4,
    filters: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    filters = filters or {}
    ranked = []
    for chunk in load_authority_chunks():
        if not chunk.get("allowed_for_rag", False):
            continue
        if int(chunk.get("authority_level", 0)) < min_authority_level:
            continue
        if filters.get("source_type") and chunk.get("source_type") != filters["source_type"]:
            continue
        if filters.get("domain"):
            domains = set(chunk.get("domain", []))
            if not domains.intersection(set(filters["domain"])):
                continue
        score = keyword_score(query, chunk)
        if score > 0:
            ranked.append((score, chunk))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [citation_from_chunk(chunk, score) for score, chunk in ranked[:top_k]]


def search_authority_knowledge(
    query: str,
    top_k: int = 8,
    filters: Optional[Dict[str, Any]] = None,
    min_authority_level: int = 4,
) -> List[Dict[str, Any]]:
    return search_authority_pdf_chunks(
        query=query,
        top_k=top_k,
        min_authority_level=min_authority_level,
        filters=filters,
    )
