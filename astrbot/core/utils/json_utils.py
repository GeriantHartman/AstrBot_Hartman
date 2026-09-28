from __future__ import annotations

import json
from typing import Any


def json_loads_no_bom(value: str | bytes | bytearray, *args: Any, **kwargs: Any) -> Any:
    """Parse JSON while tolerating a leading UTF-8 BOM in persisted text."""
    if isinstance(value, str):
        value = value.lstrip("\ufeff")
    return json.loads(value, *args, **kwargs)
