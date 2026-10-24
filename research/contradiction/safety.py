"""Write guard and tree/file digests. The guard uses a process-wide audit hook (cannot be removed once installed)."""
import hashlib
import os
import subprocess
import sys

_state = dict(active=False, allowed=(), violations=[])


def _hook(event, args):
    if not _state["active"]:
        return
    if event == "open":
        path, mode = args[0], args[1]
        if isinstance(path, int) or not isinstance(mode, str):
            return
        if any(c in mode for c in "wax+") or (isinstance(args[2], int) and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC)):
            p = os.path.abspath(os.fsdecode(path))
            if not any(p.startswith(a) for a in _state["allowed"]):
                _state["violations"].append(("open-write", p)); raise PermissionError("write outside results dir: " + p)
    elif event in ("os.remove", "os.rename", "os.rmdir", "os.mkdir", "shutil.move", "shutil.rmtree"):
        p = os.path.abspath(os.fsdecode(args[0]))
        if not any(p.startswith(a) for a in _state["allowed"]):
            _state["violations"].append((event, p)); raise PermissionError(event + " outside results dir: " + p)
    elif event == "sqlite3.connect":
        _state["violations"].append(("sqlite3.connect", str(args[0]))); raise PermissionError("database access is not allowed")
    elif event in ("socket.connect", "socket.bind"):
        _state["violations"].append((event, str(args[1]))); raise PermissionError("network access is not allowed")
    elif event == "subprocess.Popen" and not _state.get("allow_subprocess"):
        _state["violations"].append((event, str(args[0]))); raise PermissionError("subprocess not allowed")


sys.addaudithook(_hook)


class WriteGuard:
    def __init__(self, *allowed, allow_subprocess=False):
        self.allowed = tuple(os.path.abspath(a) for a in allowed); self.allow_subprocess = allow_subprocess

    def __enter__(self):
        _state.update(active=True, allowed=self.allowed, allow_subprocess=self.allow_subprocess); _state["violations"] = []
        return _state

    def __exit__(self, *a):
        _state["active"] = False


def file_digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 16), b""):
            h.update(b)
    return h.hexdigest()


def tree_digest(root, exclude_prefixes=("research/", ".git/", ".venv/", "node_modules/")):
    """sha256 of every file under root outside the excluded prefixes -> {relpath: digest}."""
    out = {}
    for d, dirs, files in os.walk(root):
        rel_d = os.path.relpath(d, root).replace("\\", "/")
        dirs[:] = [x for x in dirs if not any(((rel_d + "/" + x if rel_d != "." else x) + "/").startswith(p) for p in exclude_prefixes)]
        for f in files:
            rel = (rel_d + "/" + f) if rel_d != "." else f
            if not any(rel.startswith(p) for p in exclude_prefixes):
                out[rel] = file_digest(os.path.join(d, f))
    return out


def git(root, *args):
    return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True).stdout.strip()
