import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


ROOT_DIR = Path(__file__).resolve().parents[1]
AUTHORITY_DIR = ROOT_DIR / "authority_knowledge"
REGISTRY_PATH = AUTHORITY_DIR / "source_registry.yml"
DEFAULT_CANONICAL_PDF_DIR = AUTHORITY_DIR / "pdfs"
LEGACY_BOOK_DIR = ROOT_DIR / "知识库书籍"
CHUNKS_DIR = AUTHORITY_DIR / "chunks"
CHUNKS_PATH = CHUNKS_DIR / "authority_chunks.jsonl"

ORGANS = {
    "liver": ["liver", "hepatic", "肝脏", "肝"],
    "spleen": ["spleen", "splenic", "脾脏", "脾"],
    "stomach": ["stomach", "gastric", "胃"],
    "pancreas": ["pancreas", "pancreatic", "胰腺"],
    "gallbladder": ["gallbladder", "胆囊"],
    "kidney": ["kidney", "renal", "left kidney", "right kidney", "肾", "左肾", "右肾"],
    "aorta": ["aorta", "aortic", "主动脉"],
}
METRICS = {
    "dice": ["dice", "dsc", "sorensen"],
    "iou": ["iou", "jaccard"],
    "hd95": ["hd95", "hausdorff"],
    "surface_distance": ["surface distance", "surface-distance"],
    "pixel_count": ["pixel", "area", "percentage", "像素", "面积占比"],
}
TASKS = {
    "abdominal_ct": ["abdomen", "abdominal", "ct", "腹部"],
    "single_slice": ["slice", "single", "切片", "单切片"],
    "segmentation": ["segmentation", "分割"],
    "benchmark": ["benchmark", "challenge", "dataset"],
    "review": ["review", "validation", "人工复核", "quality"],
}


@dataclass
class AuthorityChunk:
    chunk_id: str
    source_id: str
    title: str
    filename: str
    source_url: str
    pdf_url: str
    publisher: str
    source_type: str
    authority_level: int
    domain: List[str]
    page_start: int
    page_end: int
    section_title: str
    license_note: str
    content_sha256: str
    created_at: str
    allowed_for_rag: bool
    text: str
    preview: str
    local_path: str
    organ_tags: List[str]
    metric_tags: List[str]
    task_tags: List[str]


def get_pdf_dir(pdf_dir: Optional[Path] = None) -> Path:
    if pdf_dir:
        return Path(pdf_dir)
    configured = os.getenv("AUTHORITY_PDF_DIR")
    if configured:
        return Path(configured)
    if LEGACY_BOOK_DIR.exists():
        return LEGACY_BOOK_DIR
    return DEFAULT_CANONICAL_PDF_DIR


def load_source_registry(path: Path = REGISTRY_PATH) -> Dict[str, Any]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    data.setdefault("sources", [])
    return data


def candidate_filenames(source: Dict[str, Any]) -> List[str]:
    names = [source.get("filename", "")]
    names.extend(source.get("local_filenames", []) or [])
    return [name for name in names if name]


def resolve_pdf_path(source: Dict[str, Any], pdf_dir: Path) -> Optional[Path]:
    for name in candidate_filenames(source):
        candidate = pdf_dir / name
        if candidate.exists():
            return candidate
    return None


def validate_local_pdfs(registry: Dict[str, Any], pdf_dir: Path) -> Dict[str, Any]:
    available = []
    missing = []
    for source in registry.get("sources", []):
        resolved = resolve_pdf_path(source, pdf_dir)
        record = {
            "source_id": source["id"],
            "filename": source["filename"],
            "title": source["title"],
        }
        if resolved:
            available.append({**record, "local_path": str(resolved)})
        else:
            missing.append({**record, "expected_any_of": candidate_filenames(source)})
    return {"available_pdfs": available, "missing_pdfs": missing}


def clean_page_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def remove_repeated_headers_footers(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    line_counts: Dict[str, int] = {}
    page_lines = []
    for page in pages:
        lines = [line.strip() for line in page["text"].splitlines() if line.strip()]
        page_lines.append(lines)
        for line in set(lines[:4] + lines[-4:]):
            if len(line) <= 120:
                line_counts[line] = line_counts.get(line, 0) + 1

    threshold = max(3, len(pages) // 4)
    repeated = {line for line, count in line_counts.items() if count >= threshold}
    cleaned = []
    for page, lines in zip(pages, page_lines):
        kept = [line for line in lines if line not in repeated]
        cleaned.append({"page_number": page["page_number"], "text": clean_page_text("\n".join(kept))})
    return cleaned


def extract_pdf_pages(pdf_path: Path) -> List[Dict[str, Any]]:
    try:
        from pypdf import PdfReader
    except Exception as exc:  # pragma: no cover - depends on optional local env
        raise RuntimeError("pypdf is required for local PDF ingestion. Install it with `pip install pypdf`.") from exc

    reader = PdfReader(str(pdf_path))
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        text = clean_page_text(page.extract_text() or "")
        pages.append({"page_number": index, "text": text})

    pages = remove_repeated_headers_footers(pages)
    if not any(page["text"] for page in pages):
        return [
            {
                "page_number": 1,
                "text": "No extractable text found. This PDF may be scanned. OCR is not implemented in MVP.",
                "warning": True,
            }
        ]
    return pages


def detect_tags(text: str, mapping: Dict[str, List[str]]) -> List[str]:
    lower = text.lower()
    return [tag for tag, keywords in mapping.items() if any(keyword.lower() in lower for keyword in keywords)]


def detect_section_title(text: str, fallback: str = "General") -> str:
    for raw_line in text.splitlines()[:12]:
        line = raw_line.strip()
        if not line or len(line) > 140:
            continue
        if re.match(r"^(\d+(\.\d+)*\.?\s+)?[A-Z][A-Za-z0-9,;:\-/() ]{5,}$", line):
            return line
        if re.match(r"^\d+(\.\d+)+\s+", line):
            return line
    return fallback


def split_text(text: str, chunk_size: int = 1000, overlap: int = 140) -> List[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if not paragraphs:
        paragraphs = [text.strip()] if text.strip() else []

    chunks: List[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 2 <= chunk_size:
            current = f"{current}\n\n{paragraph}".strip()
            continue
        if current:
            chunks.append(current)
        if len(paragraph) <= chunk_size:
            current = paragraph
            continue
        start = 0
        step = max(1, chunk_size - overlap)
        while start < len(paragraph):
            chunks.append(paragraph[start : start + chunk_size].strip())
            start += step
        current = ""
    if current:
        chunks.append(current)
    return [chunk for chunk in chunks if chunk]


def chunk_pdf_pages(pages: List[Dict[str, Any]], source_meta: Dict[str, Any]) -> List[AuthorityChunk]:
    created_at = datetime.now(timezone.utc).isoformat()
    chunks: List[AuthorityChunk] = []
    source_id = source_meta["id"]
    local_path = str(source_meta.get("_resolved_pdf_path", ""))
    last_section = "General"

    for page in pages:
        page_number = int(page["page_number"])
        page_text = page.get("text", "")
        if not page_text:
            continue
        section_title = detect_section_title(page_text, last_section)
        last_section = section_title
        for text in split_text(page_text):
            chunk_index = len(chunks) + 1
            content_sha256 = hashlib.sha256(
                f"{source_id}:{page_number}:{text}".encode("utf-8")
            ).hexdigest()
            chunks.append(
                AuthorityChunk(
                    chunk_id=f"{source_id}-p{page_number}-c{chunk_index}",
                    source_id=source_id,
                    title=source_meta["title"],
                    filename=source_meta["filename"],
                    source_url=source_meta["source_url"],
                    pdf_url=source_meta["pdf_url"],
                    publisher=source_meta["publisher"],
                    source_type=source_meta["source_type"],
                    authority_level=int(source_meta["authority_level"]),
                    domain=source_meta.get("domain", []),
                    page_start=page_number,
                    page_end=page_number,
                    section_title=section_title,
                    license_note=source_meta.get("license_note", ""),
                    content_sha256=content_sha256,
                    created_at=created_at,
                    allowed_for_rag=bool(source_meta.get("allowed_for_rag", False)),
                    text=text,
                    preview=text[:360],
                    local_path=local_path,
                    organ_tags=detect_tags(text, ORGANS),
                    metric_tags=detect_tags(text, METRICS),
                    task_tags=detect_tags(text, TASKS),
                )
            )
    return chunks


def write_chunks_jsonl(chunks: List[AuthorityChunk], output_path: Path = CHUNKS_PATH) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(json.dumps(asdict(chunk), ensure_ascii=False) + "\n")
