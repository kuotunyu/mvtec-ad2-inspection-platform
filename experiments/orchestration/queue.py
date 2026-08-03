from __future__ import annotations

from typing import Literal, Self, cast

from pydantic import JsonValue, model_validator

from experiments.data.manifest import REQUIRED_CATEGORIES
from inspection_platform.contracts import ModelFamily, RunSpec
from inspection_platform.contracts._base import ContractModel
from inspection_platform.contracts.dataset import MVTecAD2Category, Sha256

APPROVED_FAMILIES: tuple[ModelFamily, ...] = ("patchcore", "efficient_ad", "dinomaly")


class ExperimentStage(ContractModel):
    """Frozen inputs needed to expand one deterministic formal-run stage."""

    name: Literal["screening", "replication"]
    family_configs: dict[ModelFamily, dict[str, JsonValue]]
    dataset_manifest_sha256: Sha256
    contenders: dict[MVTecAD2Category, tuple[ModelFamily, ModelFamily]] | None = None

    @model_validator(mode="after")
    def require_complete_stage_inputs(self) -> Self:
        if set(self.family_configs) != set(APPROVED_FAMILIES):
            raise ValueError("stage must contain exactly the three approved family configs")
        if self.name == "screening":
            if self.contenders is not None:
                raise ValueError("screening stage must not contain contenders")
            return self
        if self.contenders is None or set(self.contenders) != set(REQUIRED_CATEGORIES):
            raise ValueError("replication stage requires two contenders for every category")
        for contenders in self.contenders.values():
            if len(set(contenders)) != 2:
                raise ValueError("replication contenders must be two distinct model families")
        return self


def expand_stage(stage: ExperimentStage) -> list[RunSpec]:
    """Expand screening or replication into stable category/family/seed order."""

    items: list[RunSpec] = []
    selected: dict[MVTecAD2Category, tuple[ModelFamily, ...]]
    seeds: tuple[int, ...]
    if stage.name == "screening":
        selected = {
            cast(MVTecAD2Category, category): APPROVED_FAMILIES
            for category in REQUIRED_CATEGORIES
        }
        seeds = (42,)
    else:
        assert stage.contenders is not None
        selected = {
            category: cast(tuple[ModelFamily, ...], contenders)
            for category, contenders in stage.contenders.items()
        }
        seeds = (17, 2026)

    for category, families in selected.items():
        for family in families:
            for seed in seeds:
                items.append(
                    RunSpec(
                        model_family=family,
                        category=category,
                        seed=seed,
                        config=dict(stage.family_configs[family]),
                        dataset_manifest_sha256=stage.dataset_manifest_sha256,
                    )
                )
    return sorted(items, key=lambda item: (item.category, item.model_family, item.seed))
