"""Make fully authored synthetic review snapshots visible without a live publish."""
import json
from contextlib import contextmanager

from agent_annotate import cli
from agent_annotate.review_versions import activate, shown


def complete(directory):
    drafts = directory / '.review-drafts'
    for path in sorted(drafts.glob('v*.json'), key=lambda p: int(p.stem[1:])):
        if shown(cli._read_meta(directory), path.stem):
            path.unlink()
        else:
            activate(directory, path.stem)


def checked(directory, args):
    from agent_annotate.review_versions import draft_path, fingerprint, read_draft
    from agent_annotate.sync_server import _atomic_write_json
    version = args.candidate_version
    data = read_draft(directory, version)
    data.update(verified=True, fingerprint=fingerprint(directory, version))
    _atomic_write_json(draft_path(directory, version), data)
    return 0


# UI fixtures build synthetic snapshots; publication/immutability tests use direct HTTP.
DIRECTORIES = {}


def register(base, directory):
    DIRECTORIES[base] = directory


@contextmanager
def authoring(base, body):
    directory = DIRECTORIES.get(base)
    items = body.get('items', [body]) if isinstance(body, dict) else []
    if directory is None or not any(it.get('decision_request') for it in items):
        yield
        return
    path = directory / 'current.meta.json'
    original = path.read_bytes()
    data = json.loads(original)
    data.pop('current', None)
    data['history'] = []
    path.write_text(json.dumps(data))
    try:
        yield
    finally:
        path.write_bytes(original)
