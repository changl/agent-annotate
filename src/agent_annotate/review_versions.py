"""Review versions are drafts until a complete round is committed."""
import hashlib
import json
import os
import re
import secrets
from pathlib import Path


def shown(meta, version):
    return version == meta.get('current') or any(
        h.get('version') == version for h in meta.get('history', []) if isinstance(h, dict))


def require_draft(meta, version):
    if not isinstance(version, str) or not re.fullmatch(r'v[0-9]+', version):
        raise ValueError('version is not vN · fix: --version v2 (or leave it out for the next one)')
    if shown(meta, version):
        numbers = [int(h['version'][1:]) for h in meta.get('history', [])
                   if isinstance(h, dict) and re.fullmatch(r'v[0-9]+', str(h.get('version', '')))]
        raise ValueError(f'{version} is already visible and immutable; use v{max([int(version[1:]), *numbers]) + 1}'
                         ' · fix: leave out --version and the next one is picked')


def next_version(directory):
    """One past every version the page shows, has staged or holds as a file; v1 for a new page."""
    from .cli import _read_meta
    directory = Path(directory)
    meta = _read_meta(directory) if directory.is_dir() else {}
    names = [meta.get('current'), *(h.get('version') for h in meta.get('history') or [] if isinstance(h, dict))]
    names += [p.stem for p in (directory / '.review-drafts').glob('v*.json')]
    names += [p.name[:-5] for p in (directory / 'versions').glob('v*.html')]
    numbers = [int(v[1:]) for v in names if isinstance(v, str) and re.fullmatch(r'v[0-9]+', v)]
    return f'v{max(numbers, default=0) + 1}'


def draft_path(directory, version):
    if not isinstance(version, str) or not re.fullmatch(r'v[0-9]+', version):
        raise ValueError('invalid version')
    return Path(directory) / '.review-drafts' / f'{version}.json'


def read_draft(directory, version):
    return json.loads(draft_path(directory, version).read_text(encoding='utf-8'))


def stage(directory, version, label, fixes, stats):
    from .cli import _read_meta
    from .store import write_json
    meta = _read_meta(directory)
    require_draft(meta, version)
    if fixes is not None and (not shown(meta, fixes) or int(fixes[1:]) >= int(version[1:])):
        raise ValueError('--fixes names no earlier shown version · fix: --fixes one of the versions in History')
    data = {'version': version, 'label': label, 'preview': secrets.token_urlsafe(24), **stats}
    if fixes is not None:
        data['fixes'] = fixes
    path = draft_path(directory, version)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, data)
    return data


def fingerprint(directory, version):
    digest = hashlib.sha256()
    for suffix in ('.html', '.cards.json'):
        path = Path(directory) / 'versions' / f'{version}{suffix}'
        digest.update(path.read_bytes() if path.exists() else b'')
    return digest.hexdigest()


def activate(directory, version, label=None):
    """Caller holds the comment-store lock, after every card was validated."""
    from .cli import _now_iso
    from .store import update_meta
    data = read_draft(directory, version)
    link = directory / '.current.html.ready'
    link.unlink(missing_ok=True)
    link.symlink_to(Path('versions') / f'{version}.html')

    def mutate(meta):
        require_draft(meta, version)
        entry = {k: v for k, v in data.items() if k not in ('preview', 'verified', 'fingerprint', 'reserved')}
        entry.update(ts=_now_iso(), label=label if label is not None else data['label'])
        meta.setdefault('history', []).append(entry)
        meta['current'] = version

    update_meta(directory, mutate)
    os.replace(link, directory / 'current.html')
    draft_path(directory, version).unlink(missing_ok=True)


def preview_version(directory, route):
    match = re.fullmatch(r"/__review_preview/(v[0-9]+)/([A-Za-z0-9_-]+)/?", route)
    if match:
        try:
            from .cli import _read_meta
            if shown(_read_meta(directory), match[1]):
                return None
            data = read_draft(directory, match[1])
            if secrets.compare_digest(data["preview"], match[2]):
                return match[1]
        except (OSError, ValueError, KeyError):
            pass
    return None


def visible_store(directory, store, meta):
    """Keep unpublished Review items out of reviewer responses and counts."""
    from .categories import comment_category
    published = {h.get('version') for h in meta.get('history') or [] if isinstance(h, dict)}
    published.add(meta.get('current'))
    published.discard(None)
    pending = {p.stem for p in (Path(directory) / '.review-drafts').glob('v*.json')} if not published else set()

    def visible(comment):
        version = comment.get('version')
        if not version or comment.get('doc') or comment_category(comment) != 'review':
            return True
        return version in published if published else version not in pending

    return {**store, **{area: {anchor: [c for c in items if visible(c)]
                              for anchor, items in store.get(area, {}).items()}
                       for area in ('anchors', 'archived')}}
