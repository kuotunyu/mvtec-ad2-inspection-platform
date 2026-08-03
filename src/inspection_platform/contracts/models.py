from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, computed_field, model_validator

from inspection_platform.contracts._base import ContractModel
from inspection_platform.contracts._hashing import canonical_hash
from inspection_platform.contracts.dataset import MVTecAD2Category, Sha256
from inspection_platform.contracts.experiments import ModelFamily


class BundleFile(ContractModel):
    """One content-verified file contained in a model bundle."""

    path: str
    sha256: Sha256
    size: Annotated[int, Field(ge=0)]


class ModelBundleManifest(ContractModel):
    """Serving boundary for a real champion or restricted synthetic mock."""

    category: MVTecAD2Category
    runtime_kind: Literal["anomalib", "mock"]
    model_family: ModelFamily | None
    evaluation_scope: Literal["public-selected-champion", "synthetic-ci-only"] = (
        "public-selected-champion"
    )
    files: tuple[BundleFile, ...]
    prediction_contract_version: str = "1.0.0"
    preprocessing_sha256: Sha256 | None = None
    threshold: float | None = None

    @model_validator(mode="after")
    def validate_runtime_scope(self) -> ModelBundleManifest:
        if self.runtime_kind == "anomalib":
            if self.model_family is None:
                raise ValueError("model_family is required for an anomalib bundle")
            if self.evaluation_scope != "public-selected-champion":
                raise ValueError(
                    "an anomalib bundle must use public-selected-champion evaluation scope"
                )
        else:
            if self.model_family is not None:
                raise ValueError("model_family must be null for a mock bundle")
            if self.evaluation_scope != "synthetic-ci-only":
                raise ValueError("a mock bundle must use synthetic-ci-only evaluation scope")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def identity(self) -> str:
        return canonical_hash(self)
