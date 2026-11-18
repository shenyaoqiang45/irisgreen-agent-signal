# ADR 0001: Remove the camera pipeline

- Status: accepted
- Date: 2026-11-18

## Context

The repository grew a camera-based layer on top of the BLE and projection SDKs: camera drivers (OpenCV, Hikrobot MVS), projector-to-camera calibration, laser dot detection, object tracking, vision-language-model grounding, a `project_on_target` task and the capabilities and MCP tools that exposed them.

Verifying that layer needs a calibrated camera rig, a fixed wall and a vision model, none of which every developer or customer has. The first goal is simpler: an AI agent on a PC calls MCP and the projector shows an image. That path needs none of the camera code, and the camera code was holding up verification (see [hardware-verification.md](../hardware-verification.md)).

## Decision

Remove everything that depends on a camera, in code, tests and documentation:

- `algorithms/` (calibration, coordinate mapping, detection and grounding, tracking).
- Camera drivers, the simulated camera and wall, the VLM client and the reference task in the capability SDK.
- The capabilities `camera.capture`, `calibration.*` and `tracking.*`; the `space: camera` option of `project.point` and the `region` option of `project.image`. The MCP server goes from 16 tools to 7, and loses `--camera`, `--hik` and `--exposure-us`.
- The `object-tracking` example, the camera step of `image-projection`, the camera-based `verify_transfer.py` and the integration tests.

Kept, because they only concern the projector: the BLE protocol and SDKs, `device.*`, `project.point`, `project.image` (full field), `project.clear`, `project.status`, the gray-to-1bpp conversion modes and single-dot rendering (moved into `irisgreen_capability.render`), the simulator for the device, and the MCP server.

## Consequences

- Positions are in projector pixels. An agent cannot see the wall or aim at an object.
- Full-field images need pre-mirroring on a device with mirror 0, because there is no calibration to absorb it (see [capability-spec.md](../capability-spec.md#orientation)).
- Roadmap V0.5 (reference algorithms) and V1.0 (vision to physical projection) are deferred.
- Nothing is lost: the whole camera pipeline, including the uncommitted work in progress at the time, is on the branch `archive/camera-pipeline` and in git history. To bring it back, restore the removed paths from that branch and reintroduce the capabilities behind a separate optional package, so the base SDK stays camera-free.
