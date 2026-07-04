import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agent.authority_pdf_loader import (
    AUTHORITY_DIR,
    CHUNKS_PATH,
    REGISTRY_PATH,
    chunk_pdf_pages,
    extract_pdf_pages,
    get_pdf_dir,
    load_source_registry,
    resolve_pdf_path,
    validate_local_pdfs,
)
from agent.rag_store import index_authority_chunks


MANIFEST_PATH = AUTHORITY_DIR / "manifest.json"
INDEX_STATUS_PATH = AUTHORITY_DIR / "index_status.json"


def relative_or_absolute(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT_DIR))
    except ValueError:
        return str(path)


def ingest_local_authority_pdfs(
    registry_path: Path = REGISTRY_PATH,
    pdf_dir: Optional[Path] = None,
    chunks_path: Path = CHUNKS_PATH,
) -> Dict[str, Any]:
    registry = load_source_registry(registry_path)
    resolved_pdf_dir = get_pdf_dir(pdf_dir)
    resolved_pdf_dir.mkdir(parents=True, exist_ok=True)
    chunks_path.parent.mkdir(parents=True, exist_ok=True)

    validation = validate_local_pdfs(registry, resolved_pdf_dir)
    all_chunks = []
    failed_sources = []

    for source in registry.get("sources", []):
        if not source.get("allowed_for_rag", False):
            continue
        pdf_path = resolve_pdf_path(source, resolved_pdf_dir)
        if not pdf_path:
            continue
        try:
            pages = extract_pdf_pages(pdf_path)
            source_with_path = {**source, "_resolved_pdf_path": pdf_path}
            all_chunks.extend(chunk_pdf_pages(pages, source_with_path))
        except Exception as exc:
            failed_sources.append(
                {
                    "source_id": source["id"],
                    "filename": source["filename"],
                    "local_path": str(pdf_path),
                    "error": str(exc),
                }
            )

    store_status = index_authority_chunks(all_chunks, chunks_path)
    manifest = {
        "indexed_sources": len({chunk.source_id for chunk in all_chunks}),
        "indexed_chunks": len(all_chunks),
        "missing_sources": validation["missing_pdfs"],
        "failed_sources": failed_sources,
        "available_pdfs": validation["available_pdfs"],
        "registered_sources": len(registry.get("sources", [])),
        "store_type": store_status["store_type"],
        "pdf_dir": str(resolved_pdf_dir),
        "chunks_path": relative_or_absolute(chunks_path),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    INDEX_STATUS_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    manifest = ingest_local_authority_pdfs()
    print(f"Indexed sources: {manifest['indexed_sources']}")
    print(f"Indexed chunks: {manifest['indexed_chunks']}")
    print(f"Missing PDFs: {len(manifest['missing_sources'])}")
    print(f"Store type: {manifest['store_type']}")
    print(f"Manifest: {MANIFEST_PATH.relative_to(ROOT_DIR)}")
    if manifest["failed_sources"]:
        print("Failed sources:")
        for item in manifest["failed_sources"]:
            print(f"- {item['source_id']}: {item['error']}")


if __name__ == "__main__":
    main()
