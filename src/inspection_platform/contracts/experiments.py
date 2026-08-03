from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, JsonValue, computed_field, model_validator

from inspection_platform.contracts._base import ContractModel
from inspection_platform.contracts._hashing import canonical_hash
from inspection_platform.contracts.dataset import MVTecAD2Category, Sha256

ModelFamily = Literal["patchcore", "efficient_ad", "dinomaly"]
RunStatus = Literal["pending", "running", "completed", "failed", "stopped"]


class RunSpec(ContractModel):
    """Complete immutable identity of one formal experiment unit."""

    model_family: ModelFamily
    category: MVTecAD2Category
    seed: int
    config: dict[str, JsonValue]
    dataset_manifest_sha256: Sha256 | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def identity(self) -> str:
        return canonical_hash(self)


class RunRecord(ContractModel):
    """Durable lifecycle record for one experiment specification."""

    spec: RunSpec
    status: RunStatus
    attempt: Annotated[int, Field(ge=1)] = 1
    artifacts: dict[str, Sha256] = Field(default_factory=dict)
    error: str | None = None
    code_revision: str | None = None
    config_sha256: Sha256 | None = None
    environment_lock_sha256: Sha256 | None = None
    model_revision: str | None = None
    started_at: Annotated[float, Field(ge=0)] | None = None
    finished_at: Annotated[float, Field(ge=0)] | None = None
    latency_ms: Annotated[float, Field(ge=0)] | None = None
    peak_vram_mib: Annotated[float, Field(ge=0)] | None = None
    exit_code: int | None = None

    @model_validator(mode="after")
    def require_failure_reason(self) -> RunRecord:
        terminal_with_reason = self.status in {"failed", "stopped"}
        if terminal_with_reason and not self.error:
            raise ValueError("error is required when a run has failed or stopped")
        if not terminal_with_reason and self.error:
            raise ValueError("error is allowed only when a run has failed or stopped")
        if (
            self.started_at is not None
            and self.finished_at is not None
            and self.finished_at < self.started_at
        ):
            raise ValueError("finished_at must not precede started_at")
        if self.status == "completed" and self.exit_code not in {None, 0}:
            raise ValueError("a completed run cannot have a non-zero exit_code")
        return self
