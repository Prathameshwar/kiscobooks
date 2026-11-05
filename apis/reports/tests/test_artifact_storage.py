import hashlib
import uuid

import pytest

from reports.storage.filesystem import LocalArtifactStore, chunks


def test_private_files_are_published_atomically_and_retained_after_temporary_cleanup(tmp_path):
    store = LocalArtifactStore(tmp_path / "private")
    key = uuid.uuid4().hex
    path = store.begin(key)
    with pytest.raises(FileNotFoundError):
        store.open(key, 0)
    path.write_bytes(b"first\nsecond\n")
    artifact = store.publish(key, 100)
    assert artifact.byte_count == 13
    assert artifact.content_hash == hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        store.publish(key, 100)
    store.discard_temporary(key)
    store.discard_temporary(key)
    assert b"".join(chunks(store.open(key, 13))) == b"first\nsecond\n"
    with pytest.raises(ValueError, match="size"):
        store.open(key, 12)


@pytest.mark.parametrize("key", ["../outside", "", "/absolute", "a" * 33, "A" * 32, "x" * 32])
def test_keys_cannot_address_client_paths(tmp_path, key):
    store = LocalArtifactStore(tmp_path / "private")
    for action in (store.begin, lambda value: store.open(value, 0), store.discard_temporary):
        with pytest.raises(ValueError):
            action(key)


def test_oversized_or_unexpected_temporary_files_are_not_published_or_recursively_deleted(tmp_path):
    store = LocalArtifactStore(tmp_path / "private")
    key = uuid.uuid4().hex
    path = store.begin(key)
    path.write_bytes(b"1234")
    with pytest.raises(ValueError, match="budget"):
        store.publish(key, 3)
    assert not (store.root / "objects" / key).exists()
    nested = path.parent / "unexpected"
    nested.mkdir()
    with pytest.raises(ValueError, match="links or special"):
        store.discard_temporary(key)
    assert path.exists()


def test_link_targets_are_never_opened_or_cleaned(tmp_path):
    store = LocalArtifactStore(tmp_path / "private")
    key = uuid.uuid4().hex
    path = store.begin(key)
    outside = tmp_path / "outside"
    outside.write_text("retain")
    try:
        path.symlink_to(outside)
    except OSError:
        pytest.skip("Windows symbolic link privilege unavailable")
    for action in (lambda: store.publish(key, 100), lambda: store.discard_temporary(key)):
        with pytest.raises(ValueError):
            action()
    assert outside.read_text() == "retain"
