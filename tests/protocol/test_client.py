import asyncio

import pytest

from irisgreen_ble import IrisClient, Transport, client as client_module
from irisgreen_ble import gatt_profile as G
from irisgreen_ble import protocol as P


class FakeTransport(Transport):
    """In-memory transport: answers command writes with a scripted indication."""

    def __init__(self, mtu: int = 512, reply=None):
        self._mtu = mtu
        self.reply = reply
        self.writes: list[tuple[str, bytes, bool]] = []
        self.callbacks: dict[str, object] = {}
        self.reads: dict[str, bytes] = {}

    async def connect(self) -> None: ...

    async def disconnect(self) -> None: ...

    @property
    def mtu(self) -> int:
        return self._mtu

    async def write(self, uuid, data, response):
        self.writes.append((uuid, data, response))
        if uuid == G.CHAR_MAIN_CMD and self.reply is not None:
            for frame in self.reply(data):
                self.callbacks[uuid](frame)

    async def read(self, uuid):
        if uuid not in self.reads:
            raise KeyError(uuid)
        return self.reads[uuid]

    async def start_notify(self, uuid, callback):
        self.callbacks[uuid] = callback

    async def stop_notify(self, uuid):
        self.callbacks.pop(uuid, None)


def run(coro):
    return asyncio.run(coro)


def test_command_response_ignores_status_frames():
    status = bytes.fromhex("0000012200000F00")
    t = FakeTransport(reply=lambda frame: [status, bytes([0x80, frame[0], 1, 55])])
    resp = run(IrisClient(t).send_command(P.build_read(P.CMD_BRIGHTNESS)))
    assert resp.ok and resp.data == bytes([55])
    assert t.callbacks == {}  # unsubscribed again
    assert t.writes == [(G.CHAR_MAIN_CMD, b"\x11\x00", True)]


def test_command_timeout_and_mismatch():
    t = FakeTransport(reply=lambda frame: [])
    resp = run(IrisClient(t).send_command(b"\x11\x00", timeout=0.1))
    assert not resp.ok and "timeout" in resp.error

    t = FakeTransport(reply=lambda frame: [bytes([0x80, 0x99, 1, 0])])
    resp = run(IrisClient(t).send_command(b"\x11\x00", timeout=0.1))
    assert not resp.ok and "no matching cmd" in resp.error


def test_high_level_getters():
    t = FakeTransport(reply=lambda frame: [bytes([0x80, frame[0], 2, 0x2C, 0x01])])
    assert run(IrisClient(t).get_picture_count()) == 300


def test_push_file_sequence(monkeypatch):
    monkeypatch.setattr(client_module, "START_DELAY_S", 0)
    monkeypatch.setattr(client_module, "PACKET_DELAY_S", 0)
    stream = bytes(range(256)) * 4  # 1024 bytes
    t = FakeTransport(mtu=203)  # 200-byte chunks
    run(IrisClient(t).push_file(stream, "1_1.bmp"))

    packet = P.build_file_packet(len(stream), "1_1.bmp")
    assert t.writes[0] == (G.CHAR_FILE_START, packet, True)
    assert t.writes[-1] == (G.CHAR_FILE_END, packet, True)
    data = [w for w in t.writes if w[0] == G.CHAR_FILE_DATA]
    assert [len(w[1]) for w in data] == [200, 200, 200, 200, 200, 24]
    assert all(w[2] is False for w in data)
    assert b"".join(w[1] for w in data) == stream


def test_push_file_defaults_to_minimum_mtu(monkeypatch):
    monkeypatch.setattr(client_module, "START_DELAY_S", 0)
    monkeypatch.setattr(client_module, "PACKET_DELAY_S", 0)
    t = FakeTransport(mtu=0)
    run(IrisClient(t).push_file(bytes(45), "a.bmp"))
    sizes = [len(w[1]) for w in t.writes if w[0] == G.CHAR_FILE_DATA]
    assert sizes == [20, 20, 5]


def test_load_info_tolerates_missing_characteristics():
    t = FakeTransport()
    t.reads[G.CHAR_MODEL_NUMBER] = b"IrisGreen"
    t.reads[G.CHAR_BATTERY_LEVEL] = (1234).to_bytes(4, "little")
    info = run(IrisClient(t).load_info())
    assert info.model == "IrisGreen"
    assert info.serial == ""
    assert info.battery_u32 == 1234


def test_context_manager_records_mtu():
    async def go():
        async with IrisClient(FakeTransport(mtu=247)) as c:
            return c.info.mtu

    assert run(go()) == 247
