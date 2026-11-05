"""Write-path guard: record every write of a page record file that does not
come from agent_annotate/store.py. Installed in each Python process (test
runner, CLI and server subprocesses) when ANNOTATE_WRITE_GUARD names a log."""

import builtins
import io
import os
import sys

# Run the interpreter's own sitecustomize (Homebrew's sets up site-packages) first.
_HERE = os.path.dirname(os.path.abspath(__file__))
for _entry in sys.path:
    _candidate = os.path.join(os.path.abspath(_entry or "."), "sitecustomize.py")
    if os.path.dirname(_candidate) != _HERE and os.path.isfile(_candidate):
        with open(_candidate, encoding="utf-8") as _source:
            exec(compile(_source.read(), _candidate, "exec"), {"__name__": "sitecustomize", "__file__": _candidate})
        break

LOG = os.environ.get("ANNOTATE_WRITE_GUARD")
RECORDS = {"comments.json", "current.meta.json", "project.json", "read-state.json", "seen.json",
           "categories.json", "plan-topics.json", "cards.json", "rounds.ndjson"}


def _record(path) -> bool:
    try:
        path = os.fspath(path)
    except TypeError:
        return False
    if isinstance(path, bytes):
        path = path.decode(errors="replace")
    if "/name-backups/" in path:
        return False  # copies kept for rollback, not a page
    name = os.path.basename(path)
    if name.endswith(".ndjson") and name != "rounds.ndjson":
        return path.startswith(os.environ.get("ANNOTATE_BUS_ROOT") or "\0")
    parent = os.path.basename(os.path.dirname(path))
    return (name in RECORDS or (parent == ".review-drafts" and name.endswith(".json"))
            or (name.endswith(".json") and os.path.basename(os.path.dirname(os.path.dirname(path))) == "deliveries"))


def _check(op, path) -> None:
    if not _record(path):
        return
    frame, ours = sys._getframe(2), None
    while frame is not None and ("/pathlib/" in frame.f_code.co_filename or frame.f_code.co_filename.endswith("/pathlib.py")):
        frame = frame.f_back
    if frame is not None and "/tests/" in frame.f_code.co_filename.replace(os.sep, "/"):
        return  # a test writing its own fixture, even when called back from annotate code
    while frame is not None:
        name = frame.f_code.co_filename.replace(os.sep, "/")
        if name.endswith("agent_annotate/store.py") or "/agent_annotate/hooks/" in name or "/shutil.py" in name:
            return  # the seam, the bare hook scripts (bus and cursors stay files), whole-directory copies
        if "/agent_annotate/" in name and ours is None:
            ours = f"{name.rsplit('/agent_annotate/', 1)[1]}:{frame.f_lineno} {frame.f_code.co_name}"
        frame = frame.f_back
    if ours:
        with _open(LOG, "a", encoding="utf-8") as log:
            log.write(f"{op} {os.fspath(path)} from {ours}\n")


if LOG:
    _open, _replace, _rename, _unlink = builtins.open, os.replace, os.rename, os.unlink

    def _guarded_open(file, mode="r", *args, **kwargs):
        if any(flag in mode for flag in "wax+"):
            _check("open", file)
        return _open(file, mode, *args, **kwargs)

    def _guarded_replace(src, dst, *args, **kwargs):
        _check("replace", dst)
        return _replace(src, dst, *args, **kwargs)

    def _guarded_rename(src, dst, *args, **kwargs):
        _check("rename", dst)
        return _rename(src, dst, *args, **kwargs)

    def _guarded_unlink(path, *args, **kwargs):
        _check("unlink", path)
        return _unlink(path, *args, **kwargs)

    builtins.open = io.open = _guarded_open
    os.replace, os.rename = _guarded_replace, _guarded_rename
    os.unlink = os.remove = _guarded_unlink
