"""Read-only project-bounded access. No symlinks, traversal, hard links or FIFOs."""
import hashlib
import os
import stat
from pathlib import Path, PurePosixPath

from .policy import PolicyError


def relative_parts(value):
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise PolicyError("Invalid local relative path")
    p = PurePosixPath(value)
    if p.is_absolute() or any(x in ("", ".", "..") for x in value.split("/")):
        raise PolicyError("Absolute paths and traversal are denied")
    return p.parts


class LocalFS:
    def __init__(self, project):
        self.project = Path(project).resolve()
        self.identity = hashlib.sha256(str(self.project).encode()).hexdigest()

    def open(self, relative, directory=False):
        parts = relative_parts(relative)
        fd = os.open(self.project, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for i, part in enumerate(parts):
                flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                if i < len(parts) - 1 or directory:
                    flags |= os.O_DIRECTORY
                nxt = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = nxt
            mode = os.fstat(fd)
            if not directory and (not stat.S_ISREG(mode.st_mode) or mode.st_nlink != 1):
                raise PolicyError("Only regular non-hardlinked source files are allowed")
            return fd
        except BaseException:
            os.close(fd)
            raise

    def read(self, relative, max_bytes):
        fd = self.open(relative)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if before.st_size > max_bytes:
                raise PolicyError("Source byte limit exceeded")
            raw = stream.read(max_bytes + 1)
            after = os.fstat(stream.fileno())
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise PolicyError("Source changed during read")
        if len(raw) > max_bytes:
            raise PolicyError("Source grew beyond byte limit")
        return raw

    def walk(self, root):
        fd = self.open(root, directory=True)
        try:
            yield from self._walk_fd(fd, root)
        finally:
            os.close(fd)

    def _walk_fd(self, fd, prefix):
        for name in sorted(os.listdir(fd)):
            if name.startswith(".") or name in ("node_modules", "__pycache__"):
                continue
            path = prefix + "/" + name
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):
                yield path, "symlink_denied"
            elif stat.S_ISDIR(info.st_mode):
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    yield from self._walk_fd(child, path)
                finally:
                    os.close(child)
            elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                yield path, "file"
            else:
                yield path, "nonregular_or_hardlink_denied"
