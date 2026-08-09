from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from inspection_platform.settings import Settings
from inspection_platform.worker.service import WorkerService
from scripts.build_demo_bundle import build_demo_bundle


@dataclass(frozen=True)
class SystemHarness:
    root: Path
    settings: Settings
    client: TestClient
    worker: WorkerService

    def upload(self, *names: str, corrupt: bool = False) -> dict[str, object]:
        files: list[tuple[str, tuple[str, bytes, str]]] = []
        for name in names:
            path = Path("fixtures/public-demo/images") / name
            files.append(("files", (name, path.read_bytes(), "image/png")))
        if corrupt:
            files.append(("files", ("broken.png", b"not-an-image", "image/png")))
        response = self.client.post("/api/v1/jobs", data={"category": "can"}, files=files)
        assert response.status_code == 201
        return response.json()  # type: ignore[no-any-return]


@pytest.fixture
def system_harness(tmp_path: Path) -> SystemHarness:
    registry = tmp_path / "models"
    build_demo_bundle(registry)
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'inspection.db'}",
        artifact_root=tmp_path / "artifacts",
        model_registry_root=registry,
    )
    return SystemHarness(
        root=tmp_path,
        settings=settings,
        client=TestClient(create_app(settings)),
        worker=WorkerService(settings, worker_id="system-test-worker"),
    )
