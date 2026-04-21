from __future__ import annotations

from fastapi import UploadFile

from app.core.exceptions import BadRequestException


async def read_upload_file_limited(
    file: UploadFile,
    *,
    max_bytes: int,
    chunk_size: int = 1024 * 1024,
) -> bytes:
    """Read an UploadFile into memory with a hard cap.

    Why: Starlette request size middleware can be bypassed when Content-Length is missing.
    This provides an application-level cap and avoids unbounded memory usage.
    """
    if max_bytes <= 0:
        raise BadRequestException("Invalid upload limit")

    total = 0
    chunks: list[bytes] = []

    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise BadRequestException(f"File too large (max {max_bytes // (1024 * 1024)} MB)")
        chunks.append(chunk)

    return b"".join(chunks)

