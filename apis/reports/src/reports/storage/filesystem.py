"""Opaque keys, bounded IO and atomic no-overwrite publication on a private volume.

The configured root must be a persistent directory accessible only to Reports service
accounts (0700 on POSIX; provision an equivalent ACL on Windows). Multiple hosts must
share the same durable volume. Publication requires atomic hard-link support.
"""

import hashlib
import os
import stat
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol


@dataclass(frozen=True)
class StoredObject:
    key: str
    byte_count: int
    content_hash: str


class ArtifactStore(Protocol):
    def begin(self, key: str) -> Path: ...

    def publish(self, key: str, maximum_bytes: int) -> StoredObject: ...

    def open(self, key: str, expected_bytes: int) -> BinaryIO: ...

    def discard_temporary(self, key: str) -> bool: ...


def opaque_key(value: str) -> str:
    if len(value) != 32 or uuid.UUID(hex=value).hex != value:
        raise ValueError("invalid private artifact identity")
    return value


def plain(path: Path, *, directory: bool) -> None:
    metadata = path.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or getattr(metadata, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        or not (stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode))
    ):
        raise ValueError("artifact storage cannot contain links or special files")


def sync_directory(path: Path) -> None:
    # Windows has no portable directory fsync; the volume durability contract is operational.
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


class LocalArtifactStore:
    def __init__(self, root: Path):
        if not root.is_absolute() or root.resolve() != root:
            raise ValueError("artifact root must be an absolute private directory without links")
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        plain(root, directory=True)
        if os.name != "nt" and stat.S_IMODE(root.stat().st_mode) & 0o077:
            raise ValueError("artifact root permissions must exclude group and other users")
        self.root = root
        for folder in ("temporary", "objects"):
            target = root / folder
            target.mkdir(mode=0o700, exist_ok=True)
            plain(target, directory=True)

    def location(self, folder: str, key: str) -> Path:
        if folder not in {"temporary", "objects"}:
            raise ValueError("unknown artifact area")
        plain(self.root, directory=True)
        plain(self.root / folder, directory=True)
        return self.root / folder / opaque_key(key)

    def begin(self, key: str) -> Path:
        target = self.location("temporary", key)
        target.mkdir(mode=0o700)  # Exclusive identity; retry always has its own DB artifact row.
        return target / "output"

    def publish(self, key: str, maximum_bytes: int) -> StoredObject:
        staging = self.location("temporary", key)
        plain(staging, directory=True)
        path = staging / "output"
        plain(path, directory=False)
        digest, size = hashlib.sha256(), 0
        with path.open("r+b") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                size += len(block)
                if size > maximum_bytes:
                    raise ValueError("export exceeds its byte budget")
                digest.update(block)
            os.fsync(stream.fileno())
        final = self.location("objects", key)
        # link() is atomic and fails if an object already exists; never replace retained bytes.
        os.link(path, final, follow_symlinks=False)
        sync_directory(final.parent)
        return StoredObject(key, size, digest.hexdigest())

    def open(self, key: str, expected_bytes: int) -> BinaryIO:
        path = self.location("objects", key)
        plain(path, directory=False)
        descriptor = os.open(
            path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        )
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size != expected_bytes:
                raise ValueError("retained artifact size differs from its publication evidence")
            return os.fdopen(descriptor, "rb")
        except BaseException:
            os.close(descriptor)
            raise

    def discard_temporary(self, key: str) -> bool:
        """Caller must first prove this attempt is abandoned or already published in the DB.

        Only flat scratch files are allowed. Never recurse, follow links or remove objects.
        A finalized hard link survives removal of its temporary link.
        """
        target = self.location("temporary", key)
        if not target.exists():
            return False
        plain(target, directory=True)
        children = list(target.iterdir())
        for child in children:
            plain(child, directory=False)
        for child in children:
            child.unlink()
        target.rmdir()
        return True


def chunks(stream: BinaryIO) -> Iterator[bytes]:
    try:
        yield from iter(lambda: stream.read(256 * 1024), b"")
    finally:
        stream.close()
