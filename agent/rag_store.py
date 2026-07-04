from pathlib import Path
from typing import Any, Dict, List

from agent.authority_pdf_loader import CHUNKS_PATH, AuthorityChunk, write_chunks_jsonl


def index_authority_chunks(chunks: List[AuthorityChunk], persist_path: Path = CHUNKS_PATH) -> Dict[str, Any]:
    """Persist authority chunks.

    Chroma/embedding deployments are optional for this project. The MVP always
    keeps a JSONL fallback so CI and local runs do not require a vector service.
    """
    write_chunks_jsonl(chunks, persist_path)
    return {
        "store_type": "fallback_json",
        "persist_path": str(persist_path),
        "indexed_chunks": len(chunks),
    }
