"""Private content-addressed VM disk storage; filenames never select a path."""

import base64
import binascii
import hashlib
import os
import tempfile
import uuid
from pathlib import Path

from billing_platform.errors import ConflictError, ValidationFailedError

MAX_BYTES = 10 * 1024 * 1024
MEDIA = {"application/pdf", "image/png", "image/jpeg", "text/plain"}


def decode(content: str, media_type: str) -> tuple[bytes, str]:
    try:
        data = base64.b64decode(content, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValidationFailedError("supporting file must contain valid base64") from exc
    if not 0 < len(data) <= MAX_BYTES:
        raise ValidationFailedError("supporting file must be non-empty and at most 10 MiB")
    signatures = {
        "application/pdf": data.startswith(b"%PDF-"),
        "image/png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": data.startswith(b"\xff\xd8\xff"),
    }
    if media_type == "text/plain":
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationFailedError("text supporting files must be UTF-8") from exc
        valid = b"\x00" not in data
    else:
        valid = signatures.get(media_type, False)
    if not valid:
        raise ValidationFailedError("supporting file content does not match its media type")
    return data, hashlib.sha256(data).hexdigest()


def object_key(tenant: uuid.UUID, company: uuid.UUID, voucher: uuid.UUID, digest: str) -> str:
    return f"{tenant}/{company}/purchase/{voucher}/{digest}"


def location(root: Path | None, key: str) -> Path:
    if root is None or not root.is_absolute():
        raise ConflictError("private supporting-file storage is not configured")
    parts = key.split("/")
    try:
        if len(parts) != 5 or parts[2] != "purchase":
            raise ValueError("invalid key")
        for index in (0, 1, 3):
            if str(uuid.UUID(parts[index])) != parts[index]:
                raise ValueError("invalid scope")
        if len(parts[4]) != 64 or any(char not in "0123456789abcdef" for char in parts[4]):
            raise ValueError("invalid digest")
    except ValueError as exc:
        raise ValidationFailedError("invalid supporting-file reference") from exc
    # Administrators own the root. Refuse links/reparse points in the entire path rather
    # than following a tenant directory outside that private volume.
    target = root.joinpath(*parts)
    for path in (target, *target.parents):
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise ConflictError("private supporting-file location is unavailable")
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValidationFailedError("invalid supporting-file location")
    return target


def read(root: Path | None, key: str, digest: str, size: int) -> bytes:
    try:
        target = location(root, key)
        with target.open("rb") as stream:
            data = stream.read(MAX_BYTES + 1)
    except OSError as exc:
        raise ConflictError("supporting file is unavailable; contact your administrator") from exc
    if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
        raise ConflictError("supporting file integrity verification failed")
    return data


def store(root: Path | None, key: str, data: bytes, digest: str) -> None:
    target = location(root, key)
    try:
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        location(root, key)
        # Publish a complete fsynced file atomically. An interrupted write never poisons
        # the content address; exclusive linking never replaces retained evidence.
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
        raise ConflictError("private supporting-file storage is unavailable") from exc
