"""Generic declarations for registered interactive controls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ControlKind = Literal["boolean", "choice", "color", "number", "vector"]


@dataclass(frozen=True, init=False)
class Control:
    """Override presentation defaults for one registered interactive control."""

    name: str
    min: float | None
    max: float | None
    step: float | None
    label: str | None

    def __init__(
        self,
        name: str,
        *,
        min: float | None = None,
        max: float | None = None,
        step: float | None = None,
        label: str | None = None,
    ) -> None:
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "min", min)
        object.__setattr__(self, "max", max)
        object.__setattr__(self, "step", step)
        object.__setattr__(self, "label", label)



__all__ = ["Control"]
