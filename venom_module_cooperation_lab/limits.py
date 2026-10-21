"""Frozen v1 disk and retention policy, also reported to the operator."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Limits:
    max_runs: int = 100
    retention_days: int = 14
    database_bytes: int = 512 * 1024 * 1024
    run_bytes: int = 2 * 1024 * 1024
    event_bytes: int = 64 * 1024
    minimum_free_bytes: int = 64 * 1024 * 1024

    def __post_init__(self) -> None:
        if any(value <= 0 for value in asdict(self).values()):
            raise ValueError("limits_must_be_positive")
