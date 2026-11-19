# Capability Specification (V0.3 / V0.4)

Capabilities are the semantic operations an AI agent calls. They are implemented in [sdk/capability-sdk](../sdk/capability-sdk) and exposed unchanged as MCP tools by [mcp/irisgreen-mcp-server](../mcp/irisgreen-mcp-server).

There is no camera, calibration or tracking capability ([ADR 0001](adr/0001-remove-camera-pipeline.md)). An agent cannot see the wall; all positions are in projector pixels.

- **Names** are dotted (`project.point`). MCP tool names replace the dot with an underscore (`project_point`) because several clients only accept `[A-Za-z0-9_-]`.
- **Schemas.** Each capability has a JSON input schema (`additionalProperties: false`, validated before the handler runs) and an output schema. See `Capability.input_schema` / `output_schema`, or `tools/list` over MCP.
- **Results.** Success is a JSON object with `"ok": true`. Failure is `{"ok": false, "error": {"code", "message", "details"?}}`. Capabilities never raise to the caller.
- **Coordinates.** The 640x480 projector field, origin top-left.

## Error codes

| Code | Meaning |
|---|---|
| `invalid_argument` | Bad arguments, unknown capability, unreadable image, path outside the data directory |
| `not_connected` | No device connected: call `device.connect` |
| `out_of_field` | The point lies outside the 640x480 projector field |
| `device_error` | The device rejected or failed an operation |
| `internal_error` | Unexpected failure |

## Device

| Capability | Input | Result |
|---|---|---|
| `device.connect` | `address?` BLE address; omitted = the only device in range (an error listing the devices if there are several) | identity: `model`, `serial`, `firmware`, `battery_raw`, `mtu`, `connected` (`already_connected` if repeated) |
| `device.disconnect` | none | `ok`. Playback keeps running on the device, so call `project.clear` first |
| `device.get_status` | none | `connected`, `projecting` and the identity fields |

## Projection

| Capability | Input | Result |
|---|---|---|
| `project.point` | `x`, `y` in projector pixels; `radius` 2-60 (12); `seconds` up to 3600 | `projector` position of the dot |
| `project.image` | one of `image_path` (inside the data directory) or `image_base64`; `mode` `threshold` (default), `threshold_inv`, `otsu`, `dither`, `dither_flat`, `edges`; `seconds` | `lit_pixels`. The image fills the field |
| `project.animation` | `frames`: 1-10 items, each one of `image_path` or `image_base64`; `frame_ms` 100-60000 (150, which the device's 100 ms step rounds to 200); `mode`; `seconds` | `frames`, `lit_pixels` per frame. Stores the frames in group 1 and loops them; replaces what was shown. Every frame is uploaded (about 3.5 s each) |
| `project.clear` | none | Projects black so no light is emitted |
| `project.status` | none | `projecting`, `last_projection` |

Both `project.image` and `project.animation` use only group 1 (the boot group), so the device holds one projection at a time. A single image overwrites frame 1 without clearing the group; several frames always start from a cleared group, and a single image after an animation clears it first so no stale frames play. The 10-frame limit comes from the IrisLoop project; it is not yet confirmed on this device.

### Orientation

With the device's mirror setting at 0 (the default) the wall shows a projected image horizontally mirrored. `project.image` and `project.animation` therefore mirror each image first when the runtime has `mirror_full_field` set; the MCP server sets it unless started with `--no-pre-mirror`. `project.point` is not mirrored: `x` is the projector's own coordinate.

## Not yet covered

Everything here is tested against the simulator. On real hardware only the MCP flow connect, `project.image`, `project.status`, `project.clear`, `device.disconnect` has been run (see [hardware-verification.md](hardware-verification.md)); `project.animation` has not.
