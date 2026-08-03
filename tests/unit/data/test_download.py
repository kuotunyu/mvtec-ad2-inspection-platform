from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from experiments.data.download import DatasetSource, IntegrityError, download_archive


@dataclass
class DatasetServer:
    payload: bytes
    source: DatasetSource
    server: ThreadingHTTPServer
    thread: threading.Thread
    observed_ranges: list[str] = field(default_factory=list)
    ignore_ranges: bool = False
    truncate_once_at: int | None = None


@pytest.fixture
def http_dataset_server() -> DatasetServer:
    payload = (b"official-dataset-payload" * 257) + b"tail"
    state: DatasetServer | None = None

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            assert state is not None
            range_header = self.headers.get("Range")
            if range_header:
                state.observed_ranges.append(range_header)

            if range_header and not state.ignore_ranges:
                offset = int(range_header.removeprefix("bytes=").removesuffix("-"))
                body = state.payload[offset:]
                self.send_response(206)
                self.send_header(
                    "Content-Range",
                    f"bytes {offset}-{len(state.payload) - 1}/{len(state.payload)}",
                )
            else:
                body = state.payload
                self.send_response(200)

            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if state.truncate_once_at is not None:
                truncated = state.truncate_once_at
                state.truncate_once_at = None
                self.wfile.write(body[:truncated])
                self.wfile.flush()
                self.close_connection = True
                return
            self.wfile.write(body)

        def log_message(self, _format: str, *args: object) -> None:
            del args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    source = DatasetSource(
        name="fixture",
        url=f"http://127.0.0.1:{server.server_port}/archive.tar.gz",
        expected_size=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    state = DatasetServer(payload=payload, source=source, server=server, thread=thread)
    thread.start()
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_download_resumes_partial_file(http_dataset_server: DatasetServer, tmp_path: Path) -> None:
    target = tmp_path / "dataset.tar.gz"
    Path(f"{target}.part").write_bytes(http_dataset_server.payload[:512])

    result = download_archive(http_dataset_server.source, target)

    assert result.read_bytes() == http_dataset_server.payload
    assert http_dataset_server.observed_ranges == ["bytes=512-"]
    assert not Path(f"{target}.part").exists()


def test_download_truncates_partial_when_server_ignores_range(
    http_dataset_server: DatasetServer, tmp_path: Path
) -> None:
    target = tmp_path / "dataset.tar.gz"
    Path(f"{target}.part").write_bytes(http_dataset_server.payload[:512])
    http_dataset_server.ignore_ranges = True

    download_archive(http_dataset_server.source, target)

    assert target.read_bytes() == http_dataset_server.payload
    assert http_dataset_server.observed_ranges == ["bytes=512-"]


def test_download_resumes_after_interrupted_response(
    http_dataset_server: DatasetServer,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "dataset.tar.gz"
    http_dataset_server.truncate_once_at = 512
    monkeypatch.setattr("experiments.data.download._DOWNLOAD_CHUNK_SIZE", 128)

    download_archive(http_dataset_server.source, target, max_attempts=2)

    assert target.read_bytes() == http_dataset_server.payload
    assert http_dataset_server.observed_ranges == ["bytes=512-"]


def test_download_removes_bad_complete_archive(
    http_dataset_server: DatasetServer, tmp_path: Path
) -> None:
    target = tmp_path / "dataset.tar.gz"
    target.write_bytes(b"x" * len(http_dataset_server.payload))

    with pytest.raises(IntegrityError, match="SHA-256"):
        download_archive(http_dataset_server.source, target, max_attempts=1)

    assert not target.exists()
    assert http_dataset_server.observed_ranges == []


def test_download_rejects_oversized_partial_file(
    http_dataset_server: DatasetServer, tmp_path: Path
) -> None:
    target = tmp_path / "dataset.tar.gz"
    part = Path(f"{target}.part")
    part.write_bytes(http_dataset_server.payload + b"overflow")

    with pytest.raises(IntegrityError, match="byte count"):
        download_archive(http_dataset_server.source, target)

    assert not part.exists()
