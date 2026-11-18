# Hardware Verification To-Do

Everything above the BLE layer is tested against a simulator. This checklist is the remaining acceptance work on real devices. Tick items as they are verified and note the device, firmware, OS and date next to each result.

Legend: **V0.x** is the roadmap version the item accepts.

## Phase 1 (do this first): a PC agent projects an image through MCP

The only goal for now. No camera, calibration, tracking or phones: the camera pipeline was removed ([ADR 0001](adr/0001-remove-camera-pipeline.md)). Everything else below is deferred until this is solid.

Path under test: MCP client (the agent) → `irisgreen_mcp` over stdio → capability SDK → BLE → projector.

Run (change the address to your device; it is required when several are in range):

```text
python protocol/python/bleak/verify_mcp_image.py --address 20:6E:F1:81:71:62 --seconds 10
python protocol/python/bleak/verify_mcp_image.py --simulate    # same flow, no hardware
```

[verify_mcp_image.py](../protocol/python/bleak/verify_mcp_image.py) starts the server, then calls `device_connect`, `project_image` (a generated 640x480 test image with a frame, the text `IRIS`, an arrow and a top-left dot), `project_status`, waits, then `project_clear` and `device_disconnect`. The light is cleared even if a step fails.

- [x] Server starts on hardware without `--simulate` and lists its tools with underscore names (16 tools on 2026-11-18, before the camera tools were removed; 7 now)
- [x] `device_connect` finds the device by address; `project_image` returns `ok` (31100 lit pixels); `project_status` reports projecting; `project_clear` and `device_disconnect` succeed (2026-11-18, `Iris-G-817162`, Windows, scripted MCP client)
- [x] The image is visibly on the wall (checked by eye, 2026-11-18). With the device's mirror at 0 it appeared horizontally mirrored (`IRIS` backwards, marker on the right); an image pre-mirrored by the test script appeared correct
- [x] Fix implemented: the MCP server mirrors full-field `project_image` content on hardware (`--no-pre-mirror` turns it off for a device set to mirror 1). Covered by a simulator test
- [ ] Confirm by eye that the unmodified test image, projected through the fixed server, now reads correctly (the run passed; the wall result is not yet confirmed)
- [ ] `project_point` in projector space is not mirrored: x is the projector's own coordinate, so a dot at x=100 appears at the right. Decide whether that is acceptable
- [ ] The same calls work from a real agent in a real MCP client, launched by the client application, not from a terminal. Ready-made configs: VS Code, Cursor, WorkBuddy (see the [MCP README](../mcp/irisgreen-mcp-server/README.md#client-configuration)). Per client: [ ] VS Code / Copilot, [ ] Cursor, [ ] WorkBuddy
- [x] `project_image` with `image_path` outside `--data-dir` is refused (`invalid_argument`, over MCP on the real device, 2026-11-18)
- [x] Through the shipped client config command (`.vscode/mcp.json`: interpreter plus `launch.py`, no `PYTHONPATH`, working directory `C:\`): tools list, `device_connect` (default address), `device_get_status`, `project_point`, `project_image`, `project_clear`, `device_disconnect` all succeed on the real device (2026-11-18). A scripted client, not yet VS Code, Cursor or WorkBuddy themselves
- [x] An agent completes connect, project an image, status, clear, disconnect through the MCP tools in VS Code (Copilot agent, tools loaded from `.vscode/mcp.json`, 2026-11-18). VS Code only: Cursor and WorkBuddy not yet
- [x] Idle link drop: after the first agent run the BLE link had dropped while idle and `project_clear` failed with `BleakError: Service Discovery has not been performed yet`. `IrisDevice` now checks the link before each upload and reconnects; a 75 s idle then `project_clear` succeeded on the real device (2026-11-18). Covered by a simulator test
- [ ] Ready-made configs exist for VS Code (`.vscode/mcp.json`), Cursor (`.cursor/mcp.json`) and WorkBuddy (`.mcp.json`); VS Code works with an agent, [ ] Cursor, [ ] WorkBuddy still to try. The first Cursor attempt listed 0 tools because the output schemas had no root `type: object`; fixed

Fix found on the way: the `project_image` output schema said `projector_quad` is an array, but it is `null` without a region, so strict MCP clients rejected the result. The field was removed with the camera pipeline; a test still covers a full-field image through the client.

Pass when a real agent, given only "project this image", makes the light appear on the wall and turns it off afterwards.

## PC results so far (2026-11-18)

Rig: Windows PC with a BLE adapter, `Iris-G-817162` (`20:6E:F1:81:71:62`, firmware `36130326071700`), and at the time a Hikrobot MV-CA013-A0UM camera (USB3, mono, 1280x1024) on the MVS SDK, since removed ([ADR 0001](adr/0001-remove-camera-pipeline.md)). Tools: [verify_pc.py](../protocol/python/bleak/verify_pc.py) (read-only) and `verify_transfer.py` (camera based, changes the group-1 slot; now only on branch `archive/camera-pipeline`).

| Area | Result |
|---|---|
| V0.1 GATT (PC) | **Pass.** All services and characteristics match the spec with the documented properties; MTU 512; firmware and manufacturer readable; status frames match the 8-byte shape. `B6B7CA` (firmware `36130326032001`) passes the same checks read-only. |
| Command round trips | **Pass.** Response prefix is `0x80`. Brightness, flip and keystone mode write and read back correctly; keystone angle, FOV and mirror are acknowledged and readable. Round trip about 160-220 ms. |
| Image transfer | **Pass.** 38462-byte stream in about 4.0 s (9.5 KiB/s at MTU 512). **50 of 50** consecutive uploads succeeded (mean 4.14 s) and the projection was still correct afterwards. |
| Orientation | **Finding.** With mirror 0 (the default) the camera sees the projection **horizontally mirrored**: not vertically flipped, but a solid square authored top-left appears top-right and text reads backwards. With mirror 1 it matches the authored image. The pixel packing is unchanged and correct; calibration absorbs the mirroring, but full-field images and text need mirror 1 (or pre-mirrored content). Seen by eye too (2026-11-18): `IRIS` backwards through MCP. The MCP server now pre-mirrors full-field `project_image` content by default. |
| Identity | **Finding.** This unit's Model and Serial characteristics and the SN / model / name commands return empty (never provisioned). The battery characteristic reads `0x64` = 100, which looks like a percentage. |
| Camera | **Finding (historical).** Opening a DirectShow camera before BLE breaks Bleak ("Thread is configured for Windows GUI"). The camera code is gone; if it comes back, open the camera lazily on a worker thread, after BLE. |

Settings are restored after each test (brightness 80, flip 0, keystone mode 0 and angle 0, mirror 0, FOV 2). FOV 2 (20x10) is the unit's original level, inferred from its projection footprint before any change, since it was not read first.

Still to do on PC (after Phase 1): the rest of sections 3-4 on real hardware, reconnect and interrupted-transfer behaviour, minimum safe pacing, and the Android and iOS runs.

## 0. Test setup

- [x] IrisGreen charged, firmware version recorded (`36130326071700`)
- [ ] Test wall: flat, matte, 1.5-3 m from the projector, dim room (pegboard wall, dim room; distance not measured)
- [ ] Projector and wall do not move during a test
- [ ] Devices on hand: one Windows/Linux PC with a BLE adapter, one Android phone (note OS version), one iPhone (note iOS version): PC only so far
- [x] `python -m pytest` and `flutter test` pass on the machine being used (60 Python tests after the camera removal; 37 Dart tests earlier)

## 1. V0.1 GATT Profile: connect and discover

Goal: PC, Android and iOS can connect and see the documented GATT layout.

**PC (Python + Bleak)**
- [x] `verify_pc.py` finds the device by name prefix `Iris-G` and by service UUID
- [x] Connects, reads firmware and manufacturer; model and serial are empty on this unit
- [x] Negotiated MTU is 512, matching the documented value
- [x] Every UUID in [irisgreen-gatt.json](../protocol/gatt/specification/irisgreen-gatt.json) is present with the documented properties (read, notify, write, write-without-response, indicate)
- [x] File-transfer service `adb40006-...-0001`: start / data / end characteristics match the UUID suffix mapping (not the spreadsheet order)
- [ ] Battery characteristic returns 4 bytes (`64000000`); record the value at known charge levels to settle its units
- [x] Unsolicited status frames on `adb40002` match the 8-byte `00 00 01 .. 00` shape
- [ ] Reconnect after disconnect works; connecting twice in a row does not wedge the device (a known firmware issue if a handshake is interrupted); every run so far reconnected fine, not yet tested deliberately

**Android (Flutter)**
- [ ] Runtime permissions: `BLUETOOTH_SCAN` and `BLUETOOTH_CONNECT` (Android 12+), `ACCESS_FINE_LOCATION` (Android 11 and below)
- [ ] `scanForIris` finds the device and sorts by RSSI
- [ ] `ReactiveBleTransport.connect` succeeds, MTU request returns the negotiated value
- [ ] Characteristic lookup works (long and 16-bit UUIDs both resolve)
- [ ] `loadInfo` returns the same identity as on PC
- [ ] Re-test on a second Android vendor/version if available

**iOS (Flutter)**
- [ ] `NSBluetoothAlwaysUsageDescription` set; permission prompt appears and is handled
- [ ] Scan, connect and `loadInfo` match PC and Android
- [ ] iOS identifies the device by UUID rather than MAC; confirm reconnect by that id
- [ ] Reported MTU is the one iOS negotiated (it cannot be requested)

**Acceptance (V0.1):** the three platforms report the same identity and GATT layout. Any mismatch updates `irisgreen-gatt.json` and the Dart/Python constants, and the spec test keeps them in sync.

## 2. V0.2 BLE Protocol SDK: commands and image transfer

Goal: images and commands transfer reliably on every platform.

**Commands (each platform)**
- [x] Read brightness, picture count (PC; picture count 37 on `B6B7CA`)
- [x] Set brightness (0, 50, 100) and read it back (PC); visible effect not yet checked
- [ ] Keystone mode 0-3 verified by read-back (PC); keystone angle -10, 0, 10 acknowledged but the effect and the full -70..70 range are not checked
- [ ] FOV levels 0-2 acknowledged and measured by eye (levels 0 and 1 project a much smaller footprint than 2); mirror and flip read back; flip effect not checked visually (PC)
- [ ] Play a built-in material group, stop, delete a group: custom group 1 play and stop only; delete not tested
- [x] Confirm the documented response prefix (`80`, or `08`) the device really sends; it is `80` (PC)
- [ ] Confirm status frames never get mistaken for responses under load

**Image transfer (each platform)**
- [x] Upload the 38462-byte test stream via start / data / end; the device shows the image (PC)
- [x] Orientation checked with an asymmetric test image (PC): mirrored with mirror 0, as authored with mirror 1; not vertically flipped
- [ ] Chunking verified at the real MTU 512 (509-byte chunks); the forced low-MTU fallback is not tested
- [ ] Pacing (100 ms after start, 30 ms between chunks) is sufficient (50 of 50 uploads at about 4.1 s); the minimum reliable pacing is not yet measured
- [x] Repeat upload 50 times in a row: no corruption, no hang (PC; Android and iOS not yet)
- [ ] Android and iOS output is byte-identical to PC for the same image (capture the written stream and compare)
- [ ] Interrupted transfer (move out of range, kill the app mid-upload): device recovers, next upload works
- [ ] Group 1 behaviour: overwrite `1_1.bmp` and play without deleting works (used in every run); the 10-frame limit is not confirmed

**Acceptance (V0.2):** the same image and commands produce the same result on PC, Android and iOS, with no failures in the repeat run.

## 3. V0.3 Capability SDK on real hardware

- [ ] `device.connect` with no address finds the only device; with two devices it asks for an address. Done: with two devices in range it lists both and asks for an address, and connecting by address works (2026-11-18). Not done: the single-device case
- [x] `project.point` in projector space: corners and centre land where expected (checked by eye, 2026-11-18, `Iris-G-817162`: top-left, top-right, bottom-right, bottom-left, centre)
- [ ] `project.image` with each mode (`threshold`, `otsu`, `dither`, `edges`): all four project and look right by eye (2026-11-18, test image with a gradient disc, `IRIS` and `Hello 123`); which mode suits which content is not recorded yet
- [x] `project.clear` really emits no light (checked by eye, 2026-11-18)
- [ ] One-hour playback cap and `seconds` handling match device behaviour. Done: a 6 s request played for 6.0 s and then went out by itself (by eye, 2026-11-18). Not done: the one-hour cap
- [x] Measure real upload latency per frame: each `project.point` / `project.image` call takes 3.3-3.5 s end to end (upload, stop, play), 4.65 s for a dithered image; `device.connect` takes about 2.6 s (2026-11-18, `Iris-G-817162`, Windows)
- [x] `device.disconnect` leaves playback running as documented (the dot stayed on after the BLE link dropped, by eye, 2026-11-18)
- [ ] Battery drain during a 10-minute continuous projection

## 4. V0.4 MCP server with a real agent

- [ ] `python -m irisgreen_mcp` starts without `--simulate`. Done so far: it starts and serves on hardware (2026-11-18, see Phase 1); launched from a terminal-started script, not by a client application
- [ ] Connect it to at least two MCP clients (for example VS Code / Copilot and Claude Desktop); tools list with the underscore names. Done so far: one scripted client (`mcp` Python client) lists the tools; no real client yet
- [ ] An agent completes: connect, project an image, project a point, clear. Done so far: connect, project an image, status, clear, disconnect from a scripted client (not an agent)
- [ ] Error results (`isError`) lead the agent to the correct recovery (for example `not_connected` leads to `device_connect`; several devices in range leads to passing an address)
- [ ] BLE permissions work when the server is launched by the client application, not only from a terminal
- [ ] Server shutdown (client closes) disconnects BLE
- [x] Path restriction: an agent asking for a path outside `--data-dir` is refused (over MCP on the real device, 2026-11-18)

## 5. Safety and robustness

- [ ] Laser power and mechanical limits are enforced by firmware regardless of what the SDK sends (try out-of-range brightness and keystone values at the protocol level)
- [ ] Nothing in the SDK lets a client exceed the device's own limits
- [ ] No light is left on after a crash: kill the process mid-projection and confirm behaviour; consider a watchdog or documented `project.clear` practice
- [ ] Eye-safety note and a stop procedure written down before untrained users try it
- [ ] Points and images never project outside the projector field

## 6. Record and close the loop

For each failure found:

1. Add a regression test to the simulator or the golden vectors, so it cannot come back.
2. Fix the code, the spec, or both ([gatt-profile.md](gatt-profile.md), [protocol-spec.md](protocol-spec.md)).
3. Update the status table in the [README](../README.md#7-roadmap-and-status) only when an acceptance line is fully ticked.

| Version | Verified on | Date | Notes |
|---|---|---|---|
| V0.1 | PC (Bleak, Windows), `Iris-G-817162` fw 36130326071700. Android and iOS pending | 2026-11-18 | PC passes. Model and serial are empty on this unit |
| V0.2 | PC (Bleak, Windows), same unit. Android and iOS pending | 2026-11-18 | PC passes: 50 of 50 uploads. Mirror 0 shows the image mirrored |
| V0.3 | PC (Bleak, Windows), `Iris-G-817162`, checked by eye | 2026-11-18 | Partial: points, clear, `seconds`, disconnect and the four modes pass. Open: single-device connect, one-hour cap, 10-minute battery drain, mode recommendations |
| V0.4 | | | |
