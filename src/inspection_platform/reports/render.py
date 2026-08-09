from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping
from io import StringIO
from typing import Any


def render_csv(rows: Iterable[Mapping[str, Any]]) -> str:
    materialized = list(rows)
    if not materialized:
        return ""
    output = StringIO(newline="")
    fields = sorted(materialized[0])
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(materialized)
    return output.getvalue()


__all__ = ["render_csv"]
