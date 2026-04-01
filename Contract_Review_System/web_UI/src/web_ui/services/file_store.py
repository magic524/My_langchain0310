from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from web_ui.config import WEB_UI_UPLOAD_ROOT, sanitize_filename


@dataclass(slots=True)
class StoredUpload:
    """Metadata for one uploaded file stored on disk."""

    upload_dir: Path
    file_path: Path
    original_name: str


class UploadLike(Protocol):
    """Minimal file uploader protocol used by the service layer."""

    name: str

    def getbuffer(self) -> bytes: ...


def save_uploaded_file(uploaded_file: UploadLike, *, run_id: str) -> StoredUpload:
    """Persist the uploaded file under the Web UI upload workspace."""

    safe_name = sanitize_filename(uploaded_file.name)
    upload_dir = WEB_UI_UPLOAD_ROOT / f"{run_id}_{safe_name}"
    upload_dir.mkdir(parents=True, exist_ok=True)

    target_path = upload_dir / uploaded_file.name
    target_path.write_bytes(uploaded_file.getbuffer())

    return StoredUpload(
        upload_dir=upload_dir,
        file_path=target_path.resolve(),
        original_name=uploaded_file.name,
    )
