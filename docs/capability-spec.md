# Capability Specification (V0.3 / V0.4)

Capabilities are the semantic operations an AI agent calls. They are implemented in [sdk/capability-sdk](../sdk/capability-sdk) and exposed unchanged as MCP tools by [mcp/irisgreen-mcp-server](../mcp/irisgreen-mcp-server).

- **Names** are dotted (`project.point`). MCP tool names replace the dot with an underscore (`project_point`) because several clients only accept `[A-Za-z0-9_-]`.
- **Schemas.** Each capability has a JSON input schema (`additionalProperties: false`, validated before the handler runs) and an output schema. See `Capability.input_schema` / `output_schema`, or `tools/list` over MCP.
- **Results.** Success is a JSON object with `"ok": true`. Failure is `{"ok": false, "error": {"code", "message", "details"?}}`. Capabilities never raise to the caller.
- **Coordinates.** *Projector* space is the 640x480 projector field, origin top-left. *Camera* space is pixels of the camera frame. `calibration.*` converts between them.

## Error codes

| Code | Meaning |
|---|---|
| `invalid_argument` | Bad arguments, unknown capability, unreadable image, path outside the data directory |
| `not_connected` | No device connected: call `device.connect` |
| `no_camera` | The runtime has no camera |
| `no_calibration` | Needs a calibration: call `calibration.calibrate` or `calibration.load` |
| `calibration_failed` | Dots not found, too few agree, or the fit is implausible (the scene moved) |
| `out_of_field` | The point or region lies outside the projectable area |
| `not_tracking` | No active track: call `tracking.start` |
| `tracking_lost` | The object could not be followed any more; the track was reset |
| `device_error` | The device rejected or failed an operation |
| `internal_error` | Unexpected failure |

## Device

| Capability | Input | Result |
|---|---|---|
| `device.connect` | `address?` BLE address; omitted = the only device in range | identity: `model`, `serial`, `firmware`, `battery_raw`, `mtu`, `connected` (`already_connected` if repeated) |
| `device.disconnect` | none | `ok`. Playback keeps running on the device, so call `project.clear` first |
| `device.get_status` | none | `connected`, `projecting`, `camera`, `calibrated`, `tracking` and the identity fields |

## Projection

| Capability | Input | Result |
|---|---|---|
| `project.point` | `x`, `y`; `space` `projector` (default) or `camera`; `radius` 2-60 (12); `seconds` up to 3600 | `projector` and `camera` position of the dot. `camera` space needs a calibration |
| `project.image` | one of `image_path` (inside the data directory) or `image_base64`; `mode` `threshold` (default), `threshold_inv`, `otsu`, `dither`, `dither_flat`, `edges`; `region` `[x0,y0,x1,y1]` in camera pixels; `seconds` | `lit_pixels`, `projector_quad`. Without `region` the image fills the field; with it the image is fitted inside that wall area, keeping its aspect ratio (needs calibration) |
| `project.clear` | none | Projects black so no light is emitted |
| `project.status` | none | `projecting`, `last_projection` |

## Camera

| Capability | Input | Result |
|---|---|---|
| `camera.capture` | `quality` 10-100 (80); `overlay_field` (needs calibration) outlines the projectable area in orange | `width`, `height`, `mime_type`, `image_base64`. Over MCP the JPEG arrives as image content, not as text |

## Calibration

Calibration projects a grid of dots, finds each one in the camera and solves a homography. Keep the camera, projector and wall still while it runs.

| Capability | Input | Result |
|---|---|---|
| `calibration.calibrate` | `cols` 2-8 (4), `rows` 2-8 (3), `save_path?` (JSON in the data directory) | `H` (projector to camera), `stats` (`err_mean`, `err_max`, `inliers`, `total`, ...), `saved` |
| `calibration.load` | `path` | `H`, `stats` |
| `calibration.get_mapping` | none | `H`, `stats` |
| `calibration.map_point` | `x`, `y`; `source` `camera` (default) or `projector` | `x`, `y` in the other space, `in_field` |

Calibration files are JSON (`schema: irisgreen.calibration/1`) so other platforms can read them.

## Tracking

| Capability | Input | Result |
|---|---|---|
| `tracking.start` | `bbox` `[x, y, width, height]` in camera pixels | `center`, `bbox` |
| `tracking.update` | `aim` (true), `radius` | One frame: `center`, `velocity` (px/s), `measured`, and with `aim` an `aimed` object (`projected` true with the positions, or false with a `reason` such as `out_of_field`) |
| `tracking.follow` | `duration_s` up to 600 (10), `max_frames` up to 5000 (300), `radius` | `frames`, `aimed_frames`, `last`. On loss: the `tracking_lost` error plus `frames` and `aimed_frames` |
| `tracking.stop` | none | `ok`. The light is left as it is |

The aim point leads the object by the measured upload latency, capped by `max_lead_s` (1 s) and `max_lead_px` (120 px); slow motion, a missed measurement or a reversal of direction cancels the lead.

## Reference task

`project_on_target(registry, intent, grounder)` in [tasks.py](../sdk/capability-sdk/irisgreen_capability/tasks.py) chains the capabilities: calibrate if needed, capture a frame with the field overlay, ask a vision-language model for the target, start tracking and follow it. It returns the failing `stage` (`calibrate`, `capture`, `ground`, `track`, `follow`) when something goes wrong. `openai_compatible_grounder` connects any OpenAI-compatible endpoint (Qwen, Kimi, OpenAI, local servers).

## Not yet covered

Everything here is tested against the simulator. Behaviour on a real device, with a real camera, is not verified yet.
