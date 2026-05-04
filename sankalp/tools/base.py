from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolResult:
    name: str
    status: str
    input: dict[str, Any]
    output: Any
    started_at: float
    finished_at: float

    @classmethod
    def run(cls, name: str, input: dict[str, Any], output: Any, status: str = "ok", started_at: float | None = None) -> "ToolResult":
        return cls(
            name=name,
            status=status,
            input=input,
            output=output,
            started_at=started_at or time.time(),
            finished_at=time.time(),
        )
