# Reference Algorithms (V0.5)

Pure Python, no BLE and no device. Each directory is one package with its own `pyproject.toml`; the capability SDK composes them. They are ported from the IrisLoop project and kept deliberately small.

| Package | Path | What it provides |
|---|---|---|
| `irisgreen_mapping` | [coordinate-mapping](coordinate-mapping) | `Calibration` (projector/camera homography, JSON persistence), `solve_homography` with a geometric sanity check, `place_in_camera_rect`, `render_camera_polygon`, `camera_point_to_projector` |
| `irisgreen_calibration` | [calibration](calibration) | `calibrate` / `verify`: project a dot grid, find each dot, solve the mapping. Rejects fits where too few dots agree or the mapping is implausible |
| `irisgreen_detection` | [detection](detection) | `detect_dot` (laser spot, subpixel), VLM grounding (`GROUND_PROMPT`, `regions_from_reply`, `refine_outline`), `to_1bpp` (threshold, Otsu, dither, edges) |
| `irisgreen_tracking` | [tracking](tracking) | `ConstantVelocityKalman`, `SingleObjectTracker` over a pluggable `Measurer`, `TemplateMeasurer` (reference), `aim_camera_point` (latency-aware lead), `RegionTracker` (optical-flow planar region) |

Calibration assumes a static scene: it needs the camera, projector and wall to stay still while the grid is shown, and it refuses to return a mapping that the dots do not agree on.

`TemplateMeasurer` is a dependency-free baseline. Its estimate is pulled a few pixels by the projected dot itself when the dot sits on the target; implement `Measurer` with a stronger appearance tracker for tighter aim.

Tests: [tests/algorithms](../tests/algorithms).
