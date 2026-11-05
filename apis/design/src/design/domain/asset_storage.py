"""Private content-addressed VM disk storage for brand assets (plan P4/D3, 2026-11-03).

The same adapter the Purchase PDF pipeline uses
(``apis/vouchers/src/vouchers/domain/supporting_files.py``), closing the open storage
question for Design (docs/invoice-design.md §9.2): bytes never travel through the
database, a path is never taken from a client, and nothing here trusts a client-declared
size or digest — both are measured from the bytes actually received.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import struct
import tempfile
import uuid
from pathlib import Path

from billing_platform.errors import ConflictError, ValidationFailedError

#: Raster images only; SVG and fonts are not stored as bytes yet (docs §6.3, §9.2).
SIGNATURES: dict[str, bytes] = {
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/jpeg": b"\xff\xd8\xff",
}


#: What a PDF may embed: the raster types this store accepts (WebP included).
PRINTABLE = frozenset({*SIGNATURES, "image/webp"})


def decode(content_base64: str, mime_type: str, *, max_bytes: int) -> tuple[bytes, str]:
    """Decoded bytes and their SHA-256, after the content matches its declared type."""
    try:
        data = base64.b64decode(content_base64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValidationFailedError("asset content must be valid base64") from exc
    if not 0 < len(data) <= max_bytes:
        raise ValidationFailedError(
            f"asset content must be non-empty and at most {max_bytes} bytes"
        )
    if mime_type == "image/webp":
        valid = data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    else:
        signature = SIGNATURES.get(mime_type)
        valid = signature is not None and data.startswith(signature)
    if not valid:
        raise ValidationFailedError("asset content does not match its declared media type")
    return data, hashlib.sha256(data).hexdigest()


def png_dimensions(data: bytes, mime_type: str) -> tuple[int, int] | None:
    """Width/height read from the PNG header; other formats carry none (schema allows null)."""
    if mime_type != "image/png" or len(data) < 24 or data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    if not (0 < width <= 20_000 and 0 < height <= 20_000):
        return None
    return width, height


def location(root: Path | None, key: str) -> Path:
    """The on-disk path a stored ``storage_path`` resolves to, or a refusal.

    ``key`` is the exact ``<prefix>/assets/<tenant>/<company>/<asset>.<ext>`` string this
    service itself derived and stored in the row (``tasks/assets.py::storage_path``); it is
    never accepted from a request. Refuses any symlink or reparse point anywhere on the
    path rather than merely the leaf, and refuses to resolve outside the configured root.
    """
    if root is None or not root.is_absolute():
        raise ConflictError("private asset storage is not configured")
    parts = key.split("/")
    try:
        if len(parts) != 5 or parts[1] != "assets":
            raise ValueError("invalid key")
        for index in (2, 3):
            if str(uuid.UUID(parts[index])) != parts[index]:
                raise ValueError("invalid scope")
        name, _, extension = parts[4].rpartition(".")
        if str(uuid.UUID(name)) != name or not extension:
            raise ValueError("invalid asset identity")
    except ValueError as exc:
        raise ValidationFailedError("invalid asset storage reference") from exc
    target = root.joinpath(*parts)
    for path in (target, *target.parents):
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise ConflictError("private asset storage location is unavailable")
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValidationFailedError("invalid asset storage location")
    return target


def read(root: Path | None, key: str, digest: str, size: int) -> bytes:
    try:
        target = location(root, key)
        with target.open("rb") as stream:
            data = stream.read(size + 1)
    except OSError as exc:
        raise ConflictError("asset is unavailable; contact your administrator") from exc
    if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
        raise ConflictError("asset integrity verification failed")
    return data


def store(root: Path | None, key: str, data: bytes, digest: str) -> None:
    target = location(root, key)
    try:
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        location(root, key)
        # Publish a complete fsynced file atomically. An interrupted write never poisons
        # the content address; exclusive linking never replaces an asset already stored.
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=target.parent, prefix=".upload-", delete=False
            ) as stream:
                temporary = Path(stream.name)
                os.chmod(temporary, 0o600)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, target)
            except FileExistsError:
                pass
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        read(root, key, digest, len(data))
    except OSError as exc:
        raise ConflictError("private asset storage is unavailable") from exc
