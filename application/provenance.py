"""Verify pinned source file bytes without requiring imported Git commit objects."""
import hashlib
import json
from pathlib import Path


def verify(root):
    pin=json.loads((root/'application/source-provenance.json').read_text(encoding='utf-8'))
    expected=pin['files']
    actual=set()
    for directory in pin['roots']:
        for p in (root/directory).rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts and not p.name.endswith('.pyc'):
                actual.add(p.relative_to(root).as_posix())
    failures=[]
    for name, expected_hash in expected.items():
        p=root/name
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=expected_hash:
            failures.append(name)
    extra=actual-set(expected)
    if failures or extra:
        raise AssertionError(f'Pinned source content differs: changed/missing={failures}, unexpected={sorted(extra)}')
    return dict(baseline=pin['baseline'], files=len(expected), engineTreeUnmodified=True, foundationTreeUnmodified=True, integrationTreeUnmodified=True)
