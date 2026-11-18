"""Structured errors returned to AI agents instead of raw exceptions."""

from __future__ import annotations

# Machine-readable error codes. Agents branch on these, so keep them stable.
NOT_CONNECTED = "not_connected"
OUT_OF_FIELD = "out_of_field"
INVALID_ARGUMENT = "invalid_argument"
DEVICE_ERROR = "device_error"
INTERNAL = "internal_error"


class CapabilityError(Exception):
    """A capability call failed in a way the caller can act on."""

    def __init__(self, code: str, message: str, **details):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def to_dict(self) -> dict:
        error = {"code": self.code, "message": self.message}
        if self.details:
            error["details"] = self.details
        return {"ok": False, "error": error}
