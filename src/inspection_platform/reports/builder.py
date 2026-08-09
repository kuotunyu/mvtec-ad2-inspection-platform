from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


def build_report_json(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


__all__ = ["build_report_json"]
