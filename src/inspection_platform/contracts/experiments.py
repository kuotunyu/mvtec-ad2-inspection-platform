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

    @model_validator(mode="after")
    def require_failure_reason(self) -> RunRecord:
        if self.status == "failed" and not self.error:
            raise ValueError("error is required when a run has failed")
        if self.status != "failed" and self.error:
            raise ValueError("error is allowed only when a run has failed")
        return self
