import time
import uuid
from pathlib import Path
from typing import Any

from backend.core.database import session_scope
from backend.repositories import case_repo
from backend.services.storage_service import object_store


def create_case_from_uploads(
    *,
    files: list[tuple[str, bytes]],
    modality: str,
    body_part: str,
) -> dict[str, Any]:
    case_id = f"CASE-{time.strftime('%Y%m%d')}-{str(uuid.uuid4())[:8]}"
    filenames: list[str] = []
    object_keys: list[str] = []

    for filename, content in files:
        safe_name = Path(filename).name
        object_key = f"cases/{case_id}/source/{safe_name}"
        object_store.save_bytes(object_key, content)
        filenames.append(safe_name)
        object_keys.append(object_key)

    with session_scope() as session:
        return case_repo.create_case(
            session,
            case_id=case_id,
            modality=modality,
            body_part=body_part,
            filenames=filenames,
            object_keys=object_keys,
        )


def list_cases() -> list[dict[str, Any]]:
    with session_scope() as session:
        return case_repo.list_cases(session)
