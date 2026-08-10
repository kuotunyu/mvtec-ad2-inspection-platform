from __future__ import annotations

import hashlib
import io
import json
import re
import tarfile
import tomllib
from pathlib import Path

from scripts.verify_release import verify_archive, verify_source


def test_httpx2_is_dev_only_test_client_dependency() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    production = project["project"]["dependencies"]
    development = project["dependency-groups"]["dev"]

    assert not any(item.startswith(("httpx=", "httpx<", "httpx>")) for item in production)
    assert "httpx2>=2.7,<3" in development


def _codes(root: Path) -> set[str]:
    return {finding.code for finding in verify_source(root).findings}


def test_release_rejects_private_files_beside_package_code(tmp_path: Path) -> None:
    private = tmp_path / "src/package/checkpoint.ckpt"
    private.parent.mkdir(parents=True)
    private.write_bytes(b"weights")
    assert "private_artifact" in _codes(tmp_path)


def test_release_rejects_stale_openapi_client(tmp_path: Path) -> None:
    schema = tmp_path / "apps/web/openapi.json"
    generated = tmp_path / "apps/web/src/api/generated.ts"
    generated.parent.mkdir(parents=True)
    schema.write_text('{"openapi":"3.1.0"}', encoding="utf-8")
    generated.write_text("// openapi-source-sha256: " + "0" * 64 + "\n", encoding="utf-8")
    assert "stale_openapi_client" in _codes(tmp_path)


def test_openapi_source_hash_is_stable_across_checkout_line_endings(tmp_path: Path) -> None:
    schema = tmp_path / "apps/web/openapi.json"
    generated = tmp_path / "apps/web/src/api/generated.ts"
    generated.parent.mkdir(parents=True)
    canonical = '{\n  "openapi": "3.1.0"\n}\n'
    schema.write_text(canonical.replace("\n", "\r\n"), encoding="utf-8", newline="")
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    generated.write_text(f"// openapi-source-sha256: {digest}\n", encoding="utf-8")
    assert "stale_openapi_client" not in _codes(tmp_path)


def test_release_rejects_dirty_generated_assets(tmp_path: Path) -> None:
    asset = tmp_path / "docs/assets/workflow.svg"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"changed")
    (asset.parent / "manifest.json").write_text(
        json.dumps({"assets": {"workflow.svg": "0" * 64}}), encoding="utf-8"
    )
    assert "dirty_generated_assets" in _codes(tmp_path)


def test_release_rejects_uncommitted_numeric_claims(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "**7 runs** <!-- claim:7|reports/evidence.json|/runs|len -->", encoding="utf-8"
    )
    evidence = tmp_path / "reports/evidence.json"
    evidence.parent.mkdir()
    evidence.write_text('{"runs":[1]}', encoding="utf-8")
    assert "stale_numeric_claim" in _codes(tmp_path)


def test_release_rejects_forbidden_archive_entries(tmp_path: Path) -> None:
    archive = tmp_path / "release.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo("package/uploads/private.png")
        payload = b"private"
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    assert "forbidden_archive_entry" in {item.code for item in verify_archive(archive)}


def test_release_requires_license(tmp_path: Path) -> None:
    assert "missing_license" in _codes(tmp_path)


def test_release_rejects_mutable_model_references(tmp_path: Path) -> None:
    reference = tmp_path / "config/model.json"
    reference.parent.mkdir()
    reference.write_text('{"model_reference":"latest"}', encoding="utf-8")
    assert "mutable_model_reference" in _codes(tmp_path)


def test_release_rejects_oversized_binaries(tmp_path: Path) -> None:
    binary = tmp_path / "public/bundle.bin"
    binary.parent.mkdir()
    binary.write_bytes(b"x" * (5 * 1024 * 1024 + 1))
    assert "oversized_binary" in _codes(tmp_path)


def test_release_report_does_not_expose_local_absolute_source_path(tmp_path: Path) -> None:
    report = verify_source(tmp_path)
    assert report.source == tmp_path.name


def test_ci_is_least_privilege_pinned_and_complete() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "permissions:\n  contents: read" in workflow
    assert "secrets." not in workflow
    assert "cancel-in-progress: true" in workflow
    for job in ("python", "frontend", "publication", "docker", "system"):
        assert re.search(rf"^  {job}:$", workflow, re.MULTILINE)
    uses = re.findall(r"uses: ([^\s#]+)", workflow)
    assert uses
    assert all(re.search(r"@[0-9a-f]{40}$", action) for action in uses)


def test_ci_uses_the_reviewed_node24_action_set() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    uses = re.findall(r"uses: ([^\s#]+)", workflow)
    expected = {
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1": 5,
        "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97": 4,
        "actions/setup-node@820762786026740c76f36085b0efc47a31fe5020": 3,
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a": 1,
    }

    assert set(uses) == set(expected)
    assert {action: uses.count(action) for action in expected} == expected
    for release in ("v7.0.1", "v7.0.0"):
        assert f"# {release}" in workflow


def test_ci_uses_platform_stable_docs_asset_verification() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "scripts/render_docs_assets.py --check-manifest" in workflow


def test_release_powershell_uses_cross_platform_process_contracts() -> None:
    docker = Path("scripts/docker_smoke.ps1").read_text(encoding="utf-8")
    assert 'Invoke-NativeChecked "curl.exe"' not in docker
    assert "Get-Command" in docker
    assert "-CommandType Application" in docker

    for name in ("scripts/docker_smoke.ps1", "scripts/run_system_tests.ps1"):
        script = Path(name).read_text(encoding="utf-8")
        assert "[string]$before" in script
        assert "[string]$after" in script
        assert "Compare-Object" not in script
        assert "$before -ne $after" in script


def test_clean_export_uses_only_committed_head() -> None:
    script = Path("scripts/clean_export.ps1").read_text(encoding="utf-8")
    assert '[string]$Treeish = "HEAD"' in script
    assert 'Invoke-NativeChecked "git"' in script
    assert '"--output=$archivePath", $Treeish' in script
    assert '@("sync", "--frozen", "--extra", "ml")' in script
    assert '@("ci", "--prefix", "apps/web")' in script
    assert 'Join-Path $exportRoot "apps/web/package.json"' in script
    assert "Where-Object Name -Match '\\.(?:whl|tar\\.gz)$'" in script
    assert "verify_release.py" in script


def test_container_gates_support_gitless_committed_exports() -> None:
    for name in ("scripts/docker_smoke.ps1", "scripts/run_system_tests.ps1"):
        script = Path(name).read_text(encoding="utf-8")
        assert 'Test-Path -LiteralPath (Join-Path $repoRoot ".git")' in script
        assert 'throw "SOURCE_REVISION is required outside a Git worktree"' in script


def test_hash_bound_evidence_uses_stable_lf_bytes() -> None:
    attributes = Path(".gitattributes").read_text(encoding="utf-8")
    assert re.search(r"^docs/assets/evidence/\*\.json\s+text\s+eol=lf$", attributes, re.MULTILINE)
    assert re.search(r"^docs/assets/\*\.svg\s+text\s+eol=lf$", attributes, re.MULTILINE)


def test_private_no_go_release_is_complete_and_truthful() -> None:
    evidence = json.loads(
        Path("docs/assets/evidence/release-verification.json").read_text(encoding="utf-8")
    )
    assert evidence["candidate_status"] == "PRIVATE-NO-GO"
    assert evidence["official_private_evaluation"] == {
        "official_submission_performed": True,
        "status": "DONE",
        "verdict": "PRIVATE-NO-GO",
    }
    official = Path("docs/assets/evidence/official-private-result.json")
    assert official.is_file()
    official_payload = json.loads(official.read_text(encoding="utf-8"))
    assert official_payload["verdict"] == "PRIVATE-NO-GO"
    assert official_payload["metrics"]["private"]["auc_pro_0_05"]["average"] == 31.24
    assert official_payload["metrics"]["private_mixed"]["auc_pro_0_05"]["average"] == 29.81
    assert official_payload["thresholded_metrics_available"] is False
    assert (
        evidence["sanitized_metric_artifacts"]["docs/assets/evidence/official-private-result.json"]
        == hashlib.sha256(official.read_bytes()).hexdigest()
    )
    assert re.fullmatch(r"[0-9a-f]{40}", evidence["verified_source_sha"])
    assert evidence["gates"]["gpu_product_smoke"]["source_sha"] == evidence["verified_source_sha"]
    assert evidence["gates"]["clean_export"]["source_sha"] == evidence["verified_source_sha"]
    assert set(evidence["model_bundles"]) == {
        "can",
        "fabric",
        "fruit_jelly",
        "rice",
        "sheet_metal",
        "vial",
        "wallplugs",
        "walnuts",
    }
    for row in evidence["model_bundles"].values():
        assert re.fullmatch(r"[0-9a-f]{64}", row["bundle_identity"])
        assert re.fullmatch(r"[0-9a-f]{64}", row["manifest_sha256"])
    assert evidence["lock_sha256_kind"] == "utf8-lf-canonical"
    for relative, expected in evidence["lock_sha256"].items():
        canonical = Path(relative).read_text(encoding="utf-8").replace("\r\n", "\n")
        assert hashlib.sha256(canonical.encode()).hexdigest() == expected


def test_thresholded_local_preflight_is_separate_from_official_submission() -> None:
    evidence = json.loads(
        Path("docs/assets/evidence/release-verification.json").read_text(encoding="utf-8")
    )

    assert evidence["candidate_status"] == "PRIVATE-NO-GO"
    assert evidence["submission_handoff"]["image_count"] == 4090
    assert evidence["submission_handoff"]["thresholded_png_count"] == 0
    assert evidence["submission_handoff"]["official_submission_count"] == 1

    preflight = evidence["thresholded_local_preflight"]
    assert preflight["status"] == "PASS"
    assert preflight["submitted"] is False
    assert preflight["official_metrics_available"] is False
    assert preflight["continuous_tiff_count"] == 4090
    assert preflight["thresholded_png_count"] == 4090
    assert preflight["local_official_validator"] == "PASS"
    assert preflight["calibration_method"] == ("validation_pixel_mean_plus_3_population_std")
    assert preflight["calibration_split"] == "validation/good"
    assert re.fullmatch(r"[0-9a-f]{40}", preflight["pipeline_source_sha"])
    assert re.fullmatch(r"[0-9a-f]{64}", preflight["archive_sha256"])
    assert preflight["original_archive_integrity"] == "UNCHANGED"
    assert (
        preflight["original_archive_sha256"] == (evidence["submission_handoff"]["archive_sha256"])
    )
    assert set(preflight["calibration_sha256"]) == set(evidence["model_bundles"])
    assert all(
        re.fullmatch(r"[0-9a-f]{64}", digest) for digest in preflight["calibration_sha256"].values()
    )


def test_private_no_go_release_bookkeeping_has_no_stale_pending_work() -> None:
    plan_root = Path("docs/superpowers/plans")
    unchecked: list[str] = []
    for path in sorted(plan_root.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        if re.search(r"^\*\*Status:\*\* Active$", content, re.MULTILINE):
            continue
        in_fenced_code = False
        for line in content.splitlines():
            if re.match(r"^\s*```", line):
                in_fenced_code = not in_fenced_code
                continue
            if not in_fenced_code and re.match(r"^\s*- \[ \]", line):
                unchecked.append(f"{path.name}:{line.strip()}")
    assert unchecked == []

    checklist = Path("docs/RELEASE_CHECKLIST.md").read_text(encoding="utf-8")
    assert "pending" not in checklist.lower()


def test_release_handoff_stays_at_the_authorization_boundary() -> None:
    checklist = Path("docs/RELEASE_CHECKLIST.md").read_text(encoding="utf-8")
    remote_setup = Path("docs/REMOTE_SETUP.md").read_text(encoding="utf-8")
    combined = checklist + remote_setup
    for phrase in (
        "private_submission.tar.gz",
        "25780c9e0c0a234454fa2e6a9a7d75f274d27d0434ad089549e19b0b0906ffb9",
        "no retuning",
        "explicit authorization",
        "scripts/verify_experiments.py",
        "scripts/verify_claims.py",
    ):
        assert phrase.lower() in combined.lower()
    assert "official submission performed: yes" in combined.lower()
    assert "no second submission" in combined.lower()
