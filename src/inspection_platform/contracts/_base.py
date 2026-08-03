from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

SCHEMA_VERSION = "1.0.0"


class ContractModel(BaseModel):
    """Base for immutable, versioned, fail-closed public contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SCHEMA_VERSION

    @field_validator("schema_version")
    @classmethod
    def require_supported_schema_major(cls, value: str) -> str:
        parts = value.split(".")
        if len(parts) != 3 or not all(part.isdigit() for part in parts):
            raise ValueError("schema_version must use semantic version form X.Y.Z")
        if parts[0] != SCHEMA_VERSION.split(".", maxsplit=1)[0]:
            raise ValueError(f"unsupported schema major in {value!r}")
        return value
