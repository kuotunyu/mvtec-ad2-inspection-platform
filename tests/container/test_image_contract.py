from __future__ import annotations

import re
from pathlib import Path

import yaml


def test_images_run_as_non_root() -> None:
    for name in ("api.Dockerfile", "worker.Dockerfile", "worker-gpu.Dockerfile"):
        source = (Path("deploy/docker") / name).read_text(encoding="utf-8")
        assert re.search(r"^USER\s+(?!0\b|root\b)\S+", source, re.MULTILINE)
        assert "@sha256:" in source
        assert "HEALTHCHECK" in source
        assert "README.md LICENSE" in source
        assert "ARG APP_VERSION=0.1.0" in source
        assert 'org.opencontainers.image.version="${APP_VERSION}"' in source


def test_api_image_includes_committed_evidence() -> None:
    source = Path("deploy/docker/api.Dockerfile").read_text(encoding="utf-8")
    assert "COPY docs/assets/evidence/ docs/assets/evidence/" in source


def test_context_excludes_private_material() -> None:
    rules = Path(".dockerignore").read_text(encoding="utf-8")
    for required in (
        "data",
        "runtime",
        "artifacts",
        "checkpoints",
        ".env",
        "*.pt",
        "*.ckpt",
        ".git",
    ):
        assert required in rules


def test_compose_uses_explicit_read_only_registry_and_bounded_logs() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    assert set(compose["services"]) == {"api", "worker"}
    for service in compose["services"].values():
        assert service["build"]["args"]["APP_VERSION"] == "${APP_VERSION:-0.1.0}"
        assert service["init"] is True
        assert service["restart"] == "on-failure:3"
        assert service["logging"]["options"]["max-size"] == "10m"
        assert service["read_only"] is True
        assert any("/models:ro" in volume for volume in service["volumes"])


def test_entrypoints_do_not_download_data_or_models() -> None:
    for path in Path("deploy/docker").glob("entrypoint-*.sh"):
        source = path.read_text(encoding="utf-8").lower()
        assert "curl " not in source
        assert "wget " not in source
        assert "git clone" not in source


def test_shell_entrypoints_keep_lf_line_endings_in_windows_exports() -> None:
    attributes = Path(".gitattributes").read_text(encoding="utf-8")
    assert re.search(r"^\*\.sh\s+text\s+eol=lf$", attributes, re.MULTILINE)
    for path in Path("deploy/docker").glob("entrypoint-*.sh"):
        assert b"\r\n" not in path.read_bytes()


def test_release_scripts_fail_fast_on_native_command_errors() -> None:
    for name in ("docker_smoke.ps1", "run_system_tests.ps1"):
        source = (Path("scripts") / name).read_text(encoding="utf-8")
        assert "function Invoke-NativeChecked" in source


def test_gpu_worker_profile_installs_ml_extra_and_requests_nvidia_device() -> None:
    dockerfile = Path("deploy/docker/worker-gpu.Dockerfile").read_text(encoding="utf-8")
    assert "uv sync --frozen --no-dev --extra ml --no-editable" in dockerfile
    assert re.search(r"^USER\s+(?!0\b|root\b)\S+", dockerfile, re.MULTILINE)
    compose = yaml.safe_load(Path("compose.gpu.yaml").read_text(encoding="utf-8"))
    worker = compose["services"]["worker"]
    assert worker["build"]["dockerfile"] == "deploy/docker/worker-gpu.Dockerfile"
    assert worker["build"]["args"]["APP_VERSION"] == "${APP_VERSION:-0.1.0}"
    assert worker["environment"]["INSPECTION_INFERENCE_DEVICE"] == "cuda:0"
    assert worker["gpus"] == "all"


def test_api_uses_dedicated_disk_backed_spool_volume() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    api = compose["services"]["api"]

    assert api["environment"]["TMPDIR"] == "/runtime/spool"
    assert api["environment"]["INSPECTION_SPOOL_ROOT"] == "/runtime/spool"
    assert "inspection-spool:/runtime/spool" in api["volumes"]
    assert "inspection-spool" in compose["volumes"]

    dockerfile = Path("deploy/docker/api.Dockerfile").read_text(encoding="utf-8")
    assert "TMPDIR=/runtime/spool" in dockerfile
    assert 'VOLUME ["/runtime/db", "/runtime/artifacts", "/runtime/spool"]' in dockerfile
