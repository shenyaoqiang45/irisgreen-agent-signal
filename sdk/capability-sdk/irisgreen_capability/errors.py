"""Structured errors returned to AI agents instead of raw exceptions."""

from __future__ import annotations

# Machine-readable error codes. Agents branch on these, so keep them stable.
NOT_CONNECTED = "not_connected"
NO_CAMERA = "no_camera"
NO_CALIBRATION = "no_calibration"
OUT_OF_FIELD = "out_of_field"
INVALID_ARGUMENT = "invalid_argument"
TRACKING_LOST = "tracking_lost"
NOT_TRACKING = "not_tracking"
DEVICE_ERROR = "device_error"
CALIBRATION_FAILED = "calibration_failed"
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
