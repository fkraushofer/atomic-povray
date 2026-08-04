"""POV-Ray radiosity settings."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class Radiosity:
    """Conservative general-purpose POV-Ray radiosity preset.

    Radiosity remains disabled unless an instance is supplied to
    :class:`RenderConfig` or directly to the SDL writer.
    """

    pretrace_start: float = 0.08
    pretrace_end: float = 0.01
    count: int = 100
    error_bound: float = 0.5
    recursion_limit: int = 2

    def __post_init__(self) -> None:
        for name in ("pretrace_start", "pretrace_end"):
            value = getattr(self, name)
            if not isfinite(value) or not 0 < value <= 1:
                raise ValueError(f"{name} must lie between 0 and 1")
        if self.pretrace_end > self.pretrace_start:
            raise ValueError("pretrace_end must not exceed pretrace_start")
        if not isinstance(self.count, int) or isinstance(self.count, bool):
            raise TypeError("count must be an integer")
        if self.count < 1:
            raise ValueError("count must be positive")
        if not isfinite(self.error_bound) or self.error_bound <= 0:
            raise ValueError("error_bound must be positive and finite")
        if (
            not isinstance(self.recursion_limit, int)
            or isinstance(self.recursion_limit, bool)
        ):
            raise TypeError("recursion_limit must be an integer")
        if not 1 <= self.recursion_limit <= 20:
            raise ValueError("recursion_limit must lie between 1 and 20")
