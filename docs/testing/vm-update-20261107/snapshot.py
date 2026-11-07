"""Freeze the authorized current workspace without staging or changing Git."""
from __future__ import annotations

import hashlib
import io
import json
import pathlib
import subprocess
import tarfile
from datetime import datetime, timezone

root = pathlib.Path(__file__).resolve().parents[3]
label = 'latest-build-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
output = root / '.test_artifacts/vm-update-20261107'
output.mkdir(parents=True, exist_ok=True)
listing = subprocess.run(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
                         cwd=root, capture_output=True, check=True)
excluded = {'.git', '.review-tmp', '.test_artifacts', 'node_modules', '.next', '.venv',
            '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', '.tools', '.claude'}
manifest = {}
archive = output / (label + '.tar.gz')
with tarfile.open(archive, 'w:gz') as bundle:
    for name in sorted(set(listing.stdout.decode('utf-8').split('\0'))):
        relative = pathlib.PurePosixPath(name)
        if not name or excluded.intersection(relative.parts):
            continue
        if any(part.startswith('pytest-cache-files-') for part in relative.parts):
            continue
        path = root / name
        if not path.is_file():
            continue
        if not path.resolve().is_relative_to(root):
            raise ValueError(f'External source path: {name}')
        content = path.read_bytes()
        manifest[name] = {'sha256': hashlib.sha256(content).hexdigest(), 'size': len(content)}
        member = tarfile.TarInfo(name)
        member.size = len(content)
        member.mode = 0o755 if name.endswith('.sh') else 0o644
        bundle.addfile(member, io.BytesIO(content))
    metadata = json.dumps({'label': label, 'files': manifest}, indent=2).encode()
    member = tarfile.TarInfo('release-source-manifest.json')
    member.size, member.mode = len(metadata), 0o644
    bundle.addfile(member, io.BytesIO(metadata))
info = {'label': label, 'archive': str(archive), 'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
        'file_count': len(manifest), 'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()}
(output / 'snapshot.json').write_text(json.dumps(info, indent=2), encoding='utf-8')
print(json.dumps(info, indent=2))
