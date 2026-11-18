import json
from pathlib import Path

from irisgreen_ble import gatt_profile as G

SPEC = json.loads(
    (Path(__file__).parents[2] / "protocol" / "gatt" / "specification" / "irisgreen-gatt.json").read_text()
)


def _uuids(service: str) -> dict[str, str]:
    return {k: v["uuid"] for k, v in SPEC["services"][service]["characteristics"].items()}


def test_main_service_matches_spec():
    main = SPEC["services"]["main"]
    assert main["uuid"] == G.SVC_MAIN
    chars = _uuids("main")
    assert chars["status_read"] == G.CHAR_MAIN_STATUS_READ
    assert chars["notify"] == G.CHAR_MAIN_NOTIFY
    assert chars["command"] == G.CHAR_MAIN_CMD
    assert chars["data"] == G.CHAR_MAIN_DATA
    assert chars["command2"] == G.CHAR_MAIN_CMD2


def test_file_transfer_service_matches_spec():
    assert SPEC["services"]["file_transfer"]["uuid"] == G.SVC_SECONDARY
    chars = _uuids("file_transfer")
    assert chars["file_start"] == G.CHAR_FILE_START
    assert chars["file_data"] == G.CHAR_FILE_DATA
    assert chars["file_end"] == G.CHAR_FILE_END


def test_standard_and_limits_match_spec():
    chars = _uuids("standard")
    assert chars["device_name"] == G.CHAR_DEVICE_NAME
    assert chars["battery_level"] == G.CHAR_BATTERY_LEVEL
    assert chars["model_number"] == G.CHAR_MODEL_NUMBER
    assert chars["serial_number"] == G.CHAR_SERIAL_NUMBER
    assert chars["firmware_revision"] == G.CHAR_FIRMWARE_REV
    assert chars["manufacturer_name"] == G.CHAR_MANUFACTURER
    assert SPEC["advertising"]["name_prefix"] == G.NAME_PREFIX
    assert SPEC["mtu"]["max_chunk"] == G.MAX_CHUNK


def test_is_iris_projector():
    assert G.is_iris_projector("Iris-G-B6B7CA")
    assert G.is_iris_projector(None, [G.SVC_MAIN.upper()])
    assert not G.is_iris_projector("Other", ["0000180f-0000-1000-8000-00805f9b34fb"])
