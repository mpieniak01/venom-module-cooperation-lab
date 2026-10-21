"""Stable public error codes; never expose paths or exception messages."""


class LabError(Exception):
    def __init__(self, code: str, status: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
