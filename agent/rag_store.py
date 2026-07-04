import hashlib
import math
import re
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from agent.authority_pdf_loader import CHUNKS_PATH, ROOT_DIR, AuthorityChunk, write_chunks_jsonl


CHROMA_DB_PATH = ROOT_DIR / "data" / "chroma_db"
COLLECTION_NAME = "local_pdf_authority_chunks"
EMBEDDING_DIM = 384


def tokenize_for_embedding(text: str) -> List[str]:
    return re.findall(r"[A-Za-z0-9_\-]+|[\u4e00-\u9fff]", text.lower())


def embed_text(text: str, dim: int = EMBEDDING_DIM) -> List[float]:
    """Offline hashing embedding used for local ChromaDB indexing.

    It avoids network downloads while still producing stable dense vectors for
    ChromaDB. A stronger embedding model can replace this function later.
    """
    vector = [0.0] * dim
    tokens = tokenize_for_embedding(text)
    if not tokens:
        return vector
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def embed_texts(texts: Iterable[str]) -> List[List[float]]:
    return [embed_text(text) for text in texts]


def embedding_available() -> bool:
    return callable(embed_text)


def chromadb_available() -> bool:
    try:
        import chromadb  # noqa: F401
    except Exception:
        return False
    return True


def get_chroma_client(persist_path: Path = CHROMA_DB_PATH):
    import chromadb
    from chromadb.config import Settings

    persist_path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(persist_path),
        settings=Settings(anonymized_telemetry=False),
    )


def get_chroma_collection(persist_path: Path = CHROMA_DB_PATH):
    client = get_chroma_client(persist_path)
    return client.get_collection(COLLECTION_NAME)


def list_to_metadata_value(value: Any) -> Any:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, str)):
        return value
    if value is None:
        return ""
    return str(value)


def chunk_to_chroma_metadata(chunk: AuthorityChunk) -> Dict[str, Any]:
    data = asdict(chunk)
    data.pop("text", None)
    data.pop("preview", None)
    return {key: list_to_metadata_value(value) for key, value in data.items()}


def metadata_to_citation_chunk(metadata: Dict[str, Any], document: str) -> Dict[str, Any]:
    return {
        "chunk_id": metadata["chunk_id"],
        "source_id": metadata["source_id"],
        "title": metadata["title"],
        "filename": metadata.get("filename", ""),
        "source_url": metadata["source_url"],
        "pdf_url": metadata.get("pdf_url", ""),
        "publisher": metadata["publisher"],
        "source_type": metadata.get("source_type", ""),
        "authority_level": int(metadata.get("authority_level", 0)),
        "domain": str(metadata.get("domain", "")).split(", ") if metadata.get("domain") else [],
        "page_start": int(metadata.get("page_start", 1)),
        "page_end": int(metadata.get("page_end", metadata.get("page_start", 1))),
        "section_title": metadata.get("section_title", "General"),
        "license_note": metadata.get("license_note", ""),
        "content_sha256": metadata.get("content_sha256", ""),
        "created_at": metadata.get("created_at", ""),
        "allowed_for_rag": bool(metadata.get("allowed_for_rag", True)),
        "text": document,
        "preview": document[:360],
    }


def write_chunks_to_chromadb(
    chunks: List[AuthorityChunk],
    persist_path: Path = CHROMA_DB_PATH,
    reset: bool = True,
) -> Dict[str, Any]:
    if not chromadb_available():
        raise RuntimeError("chromadb is not installed")
    if not embedding_available():
        raise RuntimeError("embedding function is not available")

    client = get_chroma_client(persist_path)
    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
    collection = client.get_or_create_collection(
        COLLECTION_NAME,
        metadata={
            "description": "Local authority PDF chunks for segmentation-grounded RAG",
            "embedding": "offline_hashing_embedding",
        },
    )

    batch_size = 256
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        documents = [chunk.text for chunk in batch]
        collection.upsert(
            ids=[chunk.chunk_id for chunk in batch],
            documents=documents,
            metadatas=[chunk_to_chroma_metadata(chunk) for chunk in batch],
            embeddings=embed_texts(documents),
        )

    return {
        "store_type": "chroma",
        "vector_store_path": str(persist_path),
        "collection_name": COLLECTION_NAME,
        "indexed_chunks": len(chunks),
        "embedding": "offline_hashing_embedding",
    }


def index_authority_chunks(
    chunks: List[AuthorityChunk],
    chunks_path: Path = CHUNKS_PATH,
    chroma_path: Path = CHROMA_DB_PATH,
) -> Dict[str, Any]:
    """Write JSONL backup first, then the formal ChromaDB vector store."""
    write_chunks_jsonl(chunks, chunks_path)
    try:
        if chroma_path.exists():
            shutil.rmtree(chroma_path)
        chroma_status = write_chunks_to_chromadb(chunks, chroma_path)
        return {
            **chroma_status,
            "jsonl_backup_path": str(chunks_path),
            "fallback_available": chunks_path.exists(),
        }
    except Exception as exc:
        return {
            "store_type": "fallback_json",
            "jsonl_backup_path": str(chunks_path),
            "vector_store_path": str(chroma_path),
            "indexed_chunks": len(chunks),
            "fallback_available": chunks_path.exists(),
            "chroma_error": str(exc),
        }


def search_chroma_chunks(
    query: str,
    top_k: int = 8,
    min_authority_level: int = 4,
    persist_path: Path = CHROMA_DB_PATH,
) -> List[Dict[str, Any]]:
    if not persist_path.exists():
        raise RuntimeError(f"ChromaDB path does not exist: {persist_path}")
    if not chromadb_available():
        raise RuntimeError("chromadb is not installed")
    if not embedding_available():
        raise RuntimeError("embedding function is not available")

    collection = get_chroma_collection(persist_path)
    result = collection.query(
        query_embeddings=[embed_text(query)],
        n_results=max(top_k * 4, top_k),
        include=["documents", "metadatas", "distances"],
    )
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    hits = []
    for document, metadata, distance in zip(documents, metadatas, distances):
        if int(metadata.get("authority_level", 0)) < min_authority_level:
            continue
        chunk = metadata_to_citation_chunk(metadata, document)
        score = 1.0 / (1.0 + float(distance or 0.0))
        hits.append({"chunk": chunk, "score": score})
        if len(hits) >= top_k:
            break
    return hits


def chroma_chunk_count(persist_path: Path = CHROMA_DB_PATH) -> Optional[int]:
    try:
        if not persist_path.exists() or not chromadb_available():
            return None
        return int(get_chroma_collection(persist_path).count())
    except Exception:
        return None
