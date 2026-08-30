from __future__ import annotations

import json
import re
import tomllib
from importlib.metadata import version as installed_version
from pathlib import Path

import yaml

from apps.api.main import create_app
from inspection_platform import __version__

RELEASE_VERSION = "0.1.1"


def _docker_default(path: str) -> str:
    source = Path(path).read_text(encoding="utf-8")
    match = re.search(r"^ARG APP_VERSION=(\S+)$", source, re.MULTILINE)
    assert match is not None
    return match.group(1)


def _compose_default(value: str) -> str:
    match = re.fullmatch(r"\$\{APP_VERSION:-(.+)\}", value)
    assert match is not None
    return match.group(1)


def test_release_version_is_consistent_across_public_build_surfaces() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    uv_lock = tomllib.loads(Path("uv.lock").read_text(encoding="utf-8"))
    web_package = json.loads(Path("apps/web/package.json").read_text(encoding="utf-8"))
    web_lock = json.loads(Path("apps/web/package-lock.json").read_text(encoding="utf-8"))
    openapi = json.loads(Path("apps/web/openapi.json").read_text(encoding="utf-8"))
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    gpu_compose = yaml.safe_load(Path("compose.gpu.yaml").read_text(encoding="utf-8"))
    locked_project = next(
        package for package in uv_lock["package"] if package["name"] == pyproject["project"]["name"]
    )

    versions = {
        "python_project": pyproject["project"]["version"],
        "python_lock": locked_project["version"],
        "python_installed": installed_version("mvtec-ad2-inspection-platform"),
        "python_runtime": __version__,
        "fastapi_runtime": create_app().version,
        "openapi_snapshot": openapi["info"]["version"],
        "web_package": web_package["version"],
        "web_lock": web_lock["version"],
        "web_lock_root": web_lock["packages"][""]["version"],
        "compose_api": _compose_default(compose["services"]["api"]["build"]["args"]["APP_VERSION"]),
        "compose_worker": _compose_default(
            compose["services"]["worker"]["build"]["args"]["APP_VERSION"]
        ),
        "compose_gpu_worker": _compose_default(
            gpu_compose["services"]["worker"]["build"]["args"]["APP_VERSION"]
        ),
        "docker_api": _docker_default("deploy/docker/api.Dockerfile"),
        "docker_worker": _docker_default("deploy/docker/worker.Dockerfile"),
        "docker_gpu_worker": _docker_default("deploy/docker/worker-gpu.Dockerfile"),
    }

    assert versions == dict.fromkeys(versions, RELEASE_VERSION)
