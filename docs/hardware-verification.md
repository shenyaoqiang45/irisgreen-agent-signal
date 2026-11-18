# Hardware Verification To-Do

Everything above the BLE layer is tested against a simulator. This checklist is the remaining acceptance work on real devices. Tick items as they are verified and note the device, firmware, OS and date next to each result.

Legend: **V0.x** is the roadmap version the item accepts.

## PC results so far (2026-11-18)

Rig: Windows PC with a BLE adapter, `Iris-G-817162` (`20:6E:F1:81:71:62`, firmware `36130326071700`), Hikrobot MV-CA013-A0UM camera (USB3, mono, 1280x1024) on the MVS SDK. Tools: [verify_pc.py](../protocol/python/bleak/verify_pc.py) (read-only) and [verify_transfer.py](../protocol/python/bleak/verify_transfer.py) (changes the group-1 slot).

| Area | Result |
|---|---|
| V0.1 GATT (PC) | **Pass.** All services and characteristics match the spec with the documented properties; MTU 512; firmware and manufacturer readable; status frames match the 8-byte shape. `B6B7CA` (firmware `36130326032001`) passes the same checks read-only. |
| Command round trips | **Pass.** Response prefix is `0x80`. Brightness, flip and keystone mode write and read back correctly; keystone angle, FOV and mirror are acknowledged and readable. Round trip about 160-220 ms. |
| Image transfer | **Pass.** 38462-byte stream in about 4.0 s (9.5 KiB/s at MTU 512). **50 of 50** consecutive uploads succeeded (mean 4.14 s) and the projection was still correct afterwards. |
| Orientation | **Finding.** With mirror 0 (the default) the camera sees the projection **horizontally mirrored**: not vertically flipped, but a solid square authored top-left appears top-right and text reads backwards. With mirror 1 it matches the authored image. The pixel packing is unchanged and correct; calibration absorbs the mirroring, but full-field images and text need mirror 1 (or pre-mirrored content). |
| Identity | **Finding.** This unit's Model and Serial characteristics and the SN / model / name commands return empty (never provisioned). The battery characteristic reads `0x64` = 100, which looks like a percentage. |
| Camera | **Finding.** Opening a DirectShow camera before BLE breaks Bleak ("Thread is configured for Windows GUI"). Cameras now open lazily on a worker thread. The Hik camera works through `HikCamera`. |

Settings are restored after each test (brightness 80, flip 0, keystone mode 0 and angle 0, mirror 0, FOV 2). FOV 2 (20x10) is the unit's original level, inferred from its projection footprint before any change, since it was not read first.

Still to do on PC: calibration, projection, tracking and the MCP server on real hardware (sections 3-7), reconnect and interrupted-transfer behaviour, minimum safe pacing, and the Android and iOS runs.

## 0. Test setup

- [x] IrisGreen charged, firmware version recorded (`36130326071700`)
- [ ] Test wall: flat, matte, 1.5-3 m from the projector, dim room (pegboard wall, dim room; distance not measured)
- [x] Camera on a fixed mount seeing the projection area (Hik MV-CA013-A0UM); exposure 60 ms used for the tests
- [ ] Camera, projector and wall do not move during calibration
- [ ] Devices on hand: one Windows/Linux PC with a BLE adapter, one Android phone (note OS version), one iPhone (note iOS version): PC only so far
- [x] `python -m pytest` and `flutter test` pass on the machine being used (115 and 37)

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
- [x] Set brightness (0, 50, 100) and read it back (PC); visible effect not yet checked by camera
- [ ] Keystone mode 0-3 verified by read-back (PC); keystone angle -10, 0, 10 acknowledged but the effect and the full -70..70 range are not checked
- [ ] FOV levels 0-2 acknowledged and measured through the camera (levels 0 and 1 project a much smaller footprint than 2); mirror and flip read back; flip effect not checked visually (PC)
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

- [ ] `device.connect` with no address finds the only device; with two devices it asks for an address
- [ ] `project.point` in projector space: corners and centre land where expected
- [ ] `project.image` with each mode (`threshold`, `otsu`, `dither`, `edges`): real brightness and legibility, record which mode suits which content
- [ ] `project.clear` really emits no light (check with the camera and by eye)
- [ ] One-hour playback cap and `seconds` handling match device behaviour
- [ ] Measure real upload latency per frame (feeds tracking lead); record the number
- [ ] `device.disconnect` leaves playback running as documented
- [ ] Battery drain during a 10-minute continuous projection

## 4. Camera and calibration

- [x] `HikCamera` opens the Hik MV-CA013-A0UM on Windows (1280x1024, mono) once the MVS SDK is installed; `OpenCvCamera` is for UVC cameras only. Frame latency and flush count not tuned
- [ ] `camera.capture` shows a sharp frame; `overlay_field` outlines the real projectable area after calibration
- [ ] `detect_dot` finds the real laser dot: record threshold, exposure and room light that work; try a bright room and a dim room
- [ ] Saturated (white) dot centre still detected
- [ ] `calibration.calibrate` succeeds; record `err_mean`, `err_max`, inliers (target: mean under 3 px at the camera's resolution)
- [ ] `verify` on five fresh points: errors are small and consistent
- [ ] Calibration is rejected when someone walks through the view or the camera is bumped
- [ ] Failure message is useful when the dot is invisible (camera exposure) 
- [ ] Calibration repeatability: run three times, compare the homographies
- [ ] Different wall angle and distance; confirm the planar assumption holds

## 5. V0.4 MCP server with a real agent

- [ ] `python -m irisgreen_mcp --hik` (or `--camera 0` for a UVC camera) starts without `--simulate`
- [ ] Connect it to at least two MCP clients (for example VS Code / Copilot and Claude Desktop); tools list with the underscore names
- [ ] An agent completes: connect, capture, calibrate, project a point, clear
- [ ] `camera_capture` image content is actually visible to the model
- [ ] Error results (`isError`) lead the agent to the correct recovery (for example `no_calibration` leads to calibrating)
- [ ] BLE permissions work when the server is launched by the client application, not only from a terminal
- [ ] Server shutdown (client closes) disconnects BLE and releases the camera
- [ ] Path restriction: an agent asking for a path outside `--data-dir` is refused

## 6. V0.5 Algorithms on real data

- [ ] `TemplateMeasurer` follows a real object at walking speed under the projected dot; record the aim error with the dot on the object (expect a few pixels of pull)
- [ ] Try a stronger `Measurer` if the error is too large, and compare
- [ ] Kalman tuning: `meas_std`, `accel_std`, `max_lost` against real motion
- [ ] Lead: measured upload latency vs `max_lead_s` and `max_lead_px`; check there is no overshoot at turn-arounds
- [ ] `RegionTracker` on a textured poster: lost-tracking behaviour is clean
- [ ] `refine_outline` (GrabCut) on real photos of the target
- [ ] `render_camera_polygon` and `place_in_camera_rect` land on the intended wall region

## 7. V1.0 end-to-end vision-to-projection

- [ ] Real VLM (Qwen3-VL, Kimi or another) via `openai_compatible_grounder`: grounding returns usable boxes on real wall photos
- [ ] Orange overlay in the prompt actually keeps targets inside the projectable area
- [ ] `examples/object-tracking/main.py --intent "..."` on three different targets
- [ ] A moving target is followed for 60 seconds; record the success rate and the failure causes
- [ ] Failure stages (`ground`, `track`, `follow`) are reported correctly on real failures
- [ ] An agent completes the task with no human input, from only the instruction

**Acceptance (V1.0):** an AI agent finishes a vision-to-physical-projection task by itself, repeatably.

## 8. Safety and robustness

- [ ] Laser power and mechanical limits are enforced by firmware regardless of what the SDK sends (try out-of-range brightness and keystone values at the protocol level)
- [ ] Nothing in the SDK lets a client exceed the device's own limits
- [ ] No light is left on after a crash: kill the process mid-projection and confirm behaviour; consider a watchdog or documented `project.clear` practice
- [ ] Eye-safety note and a stop procedure written down before untrained users try it
- [ ] Out-of-field targets never project outside the calibrated area

## 9. Record and close the loop

For each failure found:

1. Add a regression test to the simulator or the golden vectors, so it cannot come back.
2. Fix the code, the spec, or both ([gatt-profile.md](gatt-profile.md), [protocol-spec.md](protocol-spec.md)).
3. Update the status table in the [README](../README.md#7-roadmap-and-status) only when an acceptance line is fully ticked.

| Version | Verified on | Date | Notes |
|---|---|---|---|
| V0.1 | PC (Bleak, Windows), `Iris-G-817162` fw 36130326071700. Android and iOS pending | 2026-11-18 | PC passes. Model and serial are empty on this unit |
| V0.2 | PC (Bleak, Windows), same unit, Hik camera. Android and iOS pending | 2026-11-18 | PC passes: 50 of 50 uploads. Mirror 0 shows the image mirrored |
| V0.3 | | | |
| V0.4 | | | |
| V0.5 | | | |
| V1.0 | | | |
