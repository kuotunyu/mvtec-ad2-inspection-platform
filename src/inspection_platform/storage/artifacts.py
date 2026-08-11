from __future__ import annotations

import os
from _thread import RLock
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from importlib import import_module
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock, local
from time import monotonic, sleep
from typing import BinaryIO, cast


@dataclass(frozen=True)
class ArtifactRef:
    sha256: str
    media_type: str
    path: Path


_LOCKS_GUARD = Lock()
_THREAD_LOCKS: dict[Path, RLock] = {}
_LOCK_DEPTHS = local()


def _thread_lock(path: Path) -> RLock:
    with _LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(path, RLock())


def _lock_depths() -> dict[Path, int]:
    try:
        return cast(dict[Path, int], _LOCK_DEPTHS.value)
    except AttributeError:
        depths: dict[Path, int] = {}
        _LOCK_DEPTHS.value = depths
        return depths


def artifact_store_lock_path(root: Path) -> Path:
    return root.expanduser().resolve() / ".artifact-store.lock"


@contextmanager
def artifact_store_lock(root: Path, *, timeout_seconds: float = 30.0) -> Iterator[None]:
    resolved_root = root.expanduser().resolve()
    resolved_root.mkdir(parents=True, exist_ok=True)
    lock_path = artifact_store_lock_path(resolved_root)
    local_lock = _thread_lock(lock_path)
    if not local_lock.acquire(timeout=timeout_seconds):
        raise TimeoutError("timed out waiting for the artifact-store thread lock")
    depths = _lock_depths()
    if depths.get(lock_path, 0):
        depths[lock_path] += 1
        try:
            yield
        finally:
            depths[lock_path] -= 1
            local_lock.release()
        return
    handle = None
    locked = False
    try:
        handle = lock_path.open("a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            deadline = monotonic() + timeout_seconds
            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    locked = True
                    break
                except OSError:
                    if monotonic() >= deadline:
                        raise TimeoutError(
                            "timed out waiting for the artifact-store process lock"
                        ) from None
                    sleep(0.05)
        else:
            fcntl = vars(import_module("fcntl"))
            fcntl["flock"](handle.fileno(), fcntl["LOCK_EX"])
            locked = True
        depths[lock_path] = 1
        yield
    finally:
        depths.pop(lock_path, None)
        if handle is not None:
            if locked:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl = vars(import_module("fcntl"))
                    fcntl["flock"](handle.fileno(), fcntl["LOCK_UN"])
            handle.close()
        local_lock.release()


class ArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put_stream(self, stream: BinaryIO, *, media_type: str) -> ArtifactRef:
        with artifact_store_lock(self.root):
            digest = sha256()
            with NamedTemporaryFile(dir=self.root, delete=False) as temporary:
                temporary_path = Path(temporary.name)
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
                    temporary.write(chunk)
            value = digest.hexdigest()
            destination = self.root / value[:2] / value
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.is_symlink():
                    raise ValueError("artifact destination is a symbolic link")
                destination.resolve(strict=False).relative_to(self.root)
                if not destination.exists():
                    temporary_path.replace(destination)
                else:
                    temporary_path.unlink()
                    destination.touch()
            finally:
                if temporary_path.exists():
                    temporary_path.unlink()
        return ArtifactRef(value, media_type, destination)


__all__ = [
    "ArtifactRef",
    "ArtifactStore",
    "artifact_store_lock",
    "artifact_store_lock_path",
]
