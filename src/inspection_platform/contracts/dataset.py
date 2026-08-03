from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, HttpUrl, computed_field

from inspection_platform.contracts._base import ContractModel
from inspection_platform.contracts._hashing import canonical_hash

MVTecAD2Category = Literal[
    "can",
    "fabric",
    "fruit_jelly",
    "rice",
    "sheet_metal",
    "vial",
    "wallplugs",
    "walnuts",
]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class DatasetManifest(ContractModel):
    """Versioned provenance and inventory for one verified dataset tree."""

    dataset_name: Literal["mvtec_ad_2"] = "mvtec_ad_2"
    archive_url: HttpUrl
    archive_size: Annotated[int, Field(gt=0)]
    archive_sha256: Sha256
    category_counts: dict[MVTecAD2Category, dict[str, Annotated[int, Field(ge=0)]]]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def identity(self) -> str:
        return canonical_hash(self)
