# IrisGreen — AI Physical Interface

**Make AI interact with the physical world.**

[**Buy IrisGreen**](https://irisarworld.com/irisgreen/?utm_source=github&utm_medium=readme&utm_campaign=irisgreen-ai-physical-interface)

IrisGreen is an AI Physical Interface that connects AI Agents with physical devices through a standardized, cross-platform hardware capability layer.

It provides a unified software interface for AI Agents to interact with IrisGreen hardware, enabling real-world operations such as image projection, object tracking, spatial mapping, and visual interaction.

The goal is to transform IrisGreen from a hardware-controlled projection device into an extensible physical interface for AI applications.

---

## Let your AI agent put light on a wall

IrisGreen now speaks **MCP (Model Context Protocol)**. Point your AI coding or work assistant at one command and say "project this image", "loop these five frames", or "turn the light off". The agent connects to the projector over Bluetooth and does it.

| Agent | Status |
|---|---|
| **Cursor** | Verified: an agent projected through MCP tools on a real projector |
| **VS Code Copilot** (agent mode) | Verified: an agent projected through MCP tools on a real projector |
| **WorkBuddy** | Config included ([.mcp.json](.mcp.json)); real-device run still to do |
| **Kimi Work** | Standard stdio MCP server, same command; not yet run |
| **Codex** | Standard stdio MCP server, same command; not yet run |

Eight tools: connect and disconnect, show a single image, loop a 1-10 frame animation, show a dot, clear, and check status. No SDK to learn and no Bluetooth code to write.

```text
python mcp/irisgreen-mcp-server/launch.py --simulate   # try it with no hardware
python mcp/irisgreen-mcp-server/launch.py              # real IrisGreen over Bluetooth
```

Setup for each client, including Codex (`~/.codex/config.toml`), is in the [MCP server guide](mcp/irisgreen-mcp-server/README.md#client-configuration).

---

## 1. Project Vision

Traditional AI interfaces primarily operate in digital environments:

- Text and chat interfaces
- APIs and software tools
- Computer Use and GUI automation

IrisGreen extends AI interaction into the physical world.

An AI Agent should be able to:

1. Understand the physical interaction task.
2. Generate or select an appropriate algorithm.
3. Convert the task into standardized hardware capabilities.
4. Execute commands through the IrisGreen device.
5. Observe execution results and adjust its behavior.

**Core principle:**

Separate hardware communication, physical capabilities, algorithms, and AI orchestration.

The hardware interface should remain stable while AI-generated algorithms and applications evolve independently.

---

## 2. System Architecture

The system is divided into five logical layers.

```text
                  AI Applications
                         |
                  AI Agent / LLM
                         |
                 MCP Server / Tools
                         |
                  Capability SDK
                         |
                 BLE Protocol SDK
                         |
                 IrisGreen GATT
                         |
                  IrisGreen Device
```

### Layer 1 — IrisGreen GATT Profile

Defines the standardized BLE communication contract between IrisGreen hardware and external clients.

Responsibilities:

- GATT Service and Characteristic definitions
- UUID specifications
- Read / Write / Notify properties
- Command and response formats
- Data packet definitions
- Error codes and device status
- Protocol versioning

This layer defines WHAT the device exposes, not HOW different platforms implement BLE communication.

The GATT specification should remain platform-independent.

### Layer 2 — BLE Protocol SDK

Provides cross-platform BLE communication and protocol implementation.

Responsibilities:

- BLE device discovery
- Connection and disconnection
- GATT service discovery
- Characteristic read / write / notify
- Packet fragmentation and reassembly
- Data transmission and retransmission
- Connection state management
- Protocol serialization and deserialization

Target platforms:

- Android
- iOS
- Windows / Linux PC

Reference implementations:

- Python + Bleak: existing PC implementation and protocol reference.
- Flutter: cross-platform mobile implementation for Android and iOS.

The goal is to implement the same IrisGreen GATT protocol across platforms without changing device firmware.

### Layer 3 — Capability SDK

Provides high-level physical device capabilities.

AI applications should not need to understand BLE characteristics or packet formats.

Instead, they interact with semantic APIs.

Initial capabilities:

**Projection**
- project.point(x, y)
- project.image(image)
- project.clear()
- project.status()

**Device Control**
- device.connect()
- device.disconnect()
- device.get_status()

Camera, calibration and tracking capabilities were removed for now; see [ADR 0001](docs/adr/0001-remove-camera-pipeline.md).

The Capability SDK translates high-level operations into BLE Protocol SDK commands.

### Layer 4 — MCP Server / Agent Tools

Exposes IrisGreen capabilities to AI Agents through standardized tool interfaces.

Responsibilities:

- Expose device capabilities as AI-callable tools.
- Translate Agent tool calls into Capability SDK operations.
- Manage task execution and command sequencing.
- Return device status and execution results.
- Support AI-generated algorithms and dynamic task orchestration.

Example:

An AI Agent receives the instruction:

"Track the selected object and project a green laser point onto it."

The Agent can:

1. Select or generate a suitable tracking algorithm.
2. Obtain object coordinates.
3. Apply spatial calibration.
4. Invoke project.point(x, y).
5. Monitor execution and update coordinates.

**Important:** MCP is the Agent-facing interface, not the BLE communication implementation.

The MCP execution environment must have access to the local BLE-capable device runtime. MCP does not independently bypass iOS or Android BLE permissions.

### Layer 5 — AI Algorithms / Applications

Algorithms are independent, pluggable components.

They should not be tightly coupled to BLE or GATT.

Potential algorithms:

- Object detection
- Object tracking
- Visual segmentation
- Camera calibration
- Camera-to-projector coordinate mapping
- Motion prediction
- Spatial interaction

Algorithm implementations can come from:

- AI Agent generated code
- Existing open-source algorithms
- User-provided implementations
- Optimized native implementations

The Agent chooses and orchestrates algorithms according to the task.

The Capability SDK provides the stable execution interface.

---

## 3. Core Design Principles

### 3.1 Hardware / Software Decoupling

The GATT Profile defines the communication contract.

The BLE Protocol SDK implements communication.

The Capability SDK abstracts physical operations.

AI Agents operate on capabilities rather than hardware details.

### 3.2 Algorithm Independence

Algorithms must not be embedded into the BLE communication layer.

Tracking, detection, segmentation, and spatial mapping should be independently replaceable.

### 3.3 AI-Native Architecture

The system should be designed for AI Agent interaction from the beginning.

Capabilities should have:

- Clear semantic names
- Explicit input and output schemas
- Structured error handling
- Observable execution states
- Machine-readable documentation

### 3.4 Cross-Platform Support

The same hardware protocol and capability definitions should work across Android, iOS, and PC.

Platform-specific BLE implementations should be isolated behind a common interface.

### 3.5 Hardware Safety

Physical safety constraints must be enforced by firmware or another trusted execution layer.

Examples:

- Laser power limits
- Mechanical operating limits
- Emergency stop
- Device-side command validation

AI-generated algorithms must never bypass hardware safety constraints.

---

## 4. Initial Development Scope

### Phase 1 — Protocol Foundation

- Document IrisGreen GATT Profile.
- Extract and standardize existing Python + Bleak implementation.
- Define protocol data structures.
- Validate connection, read, write, and notification operations.

### Phase 2 — Cross-Platform BLE

- Build Flutter BLE POC.
- Implement Android BLE communication.
- Implement iOS BLE communication.
- Reproduce the existing PC communication workflow.
- Validate the same GATT protocol across platforms.

### Phase 3 — Capability SDK

- Implement device connection capabilities.
- Implement projection capabilities.
- Implement image / 1bpp transmission.
- Implement device status and error reporting.
- Define calibration and coordinate mapping interfaces.

### Phase 4 — MCP Integration

- Expose Capability SDK operations as MCP tools.
- Implement Agent-callable device operations.
- Support structured inputs and outputs.
- Validate AI Agent to physical device execution.

### Phase 5 — AI Physical Applications

- Integrate object tracking.
- Integrate visual perception.
- Support AI-generated algorithm implementations.
- Build end-to-end physical interaction applications.

---

## 5. Non-Goals

The initial refactoring is NOT intended to:

- Redesign the existing hardware firmware.
- Replace the existing GATT communication protocol without necessity.
- Couple tracking algorithms to BLE communication.
- Implement a monolithic AI Agent inside the device.
- Require every algorithm to be implemented in Flutter.
- Make MCP responsible for low-level BLE communication.

The priority is to establish stable interfaces and independent software layers.

---

## 6. Long-Term Vision

IrisGreen is not simply a laser projection device.

It is a physical interaction interface that allows AI Agents to connect digital intelligence with real-world actions.

The long-term architecture should support new hardware, new sensors, new algorithms, and new AI Agents without redesigning the entire system.

**Stable hardware interfaces.  
Composable physical capabilities.  
Replaceable intelligence.  
AI-native physical interaction.**

---

## 7. Roadmap and Status

| Version | Goal | Acceptance | Status |
|---|---|---|---|
| V0.1 | IrisGreen GATT Profile | PC, Android and iOS can connect | Specified and implemented ([docs](docs/gatt-profile.md)). **Verified on PC** with a real IrisGreen; Android and iOS not yet verified |
| V0.2 | BLE Protocol SDK | Images and commands transfer across platforms | Python and Flutter SDKs agree on shared golden vectors. **Verified on PC**: commands, and 50 of 50 image uploads on a real device; Android and iOS not yet verified |
| V0.3 | Capability SDK | Unified projection and status interfaces | Implemented ([spec](docs/capability-spec.md)), tested against the simulator. No camera ([ADR 0001](docs/adr/0001-remove-camera-pipeline.md)) |
| V0.4 | MCP Server | An AI Agent can call the device | Implemented, 8 tools, tested over in-memory and stdio MCP. A scripted MCP client projected an image on a real device (`project_animation` is simulator-only so far) |
| V0.5 | Reference Algorithms | Reference tracking, calibration and mapping | Removed with the camera pipeline; recoverable from branch `archive/camera-pipeline` |
| V1.0 | AI Physical Interface | An AI Agent completes a vision-to-physical-projection task on its own | Deferred until a camera is reintroduced |

Everything above the BLE layer is verified against a simulator that speaks the real protocol. Verification on real hardware is the remaining acceptance work, tracked in the [hardware verification to-do list](docs/hardware-verification.md).

## 8. Repository Layout

```text
docs/                         architecture, GATT profile, protocol and capability specs, ADRs
protocol/
  gatt/specification/         machine-readable GATT profile (V0.1)
  python/bleak/               PC transport (Python + Bleak) and hardware check scripts
  flutter/ble/                Android and iOS SDK and transport (Dart)
sdk/
  ble-protocol-sdk/           commands, image packing, IrisClient (V0.2)
  capability-sdk/             capabilities, runtime, rendering, simulator (V0.3)
mcp/irisgreen-mcp-server/     MCP server (V0.4)
examples/                     basic-projection, image-projection
tests/                        protocol, cross-platform, capability, mcp
```

## 9. Quick Start

Need the hardware? [Buy IrisGreen](https://irisarworld.com/irisgreen/?utm_source=github&utm_medium=readme&utm_campaign=irisgreen-ai-physical-interface). Everything below also runs without it, against the built-in simulator.

```text
pip install -r requirements.txt
python -m pytest                                      # Python tests (simulated hardware)
cd protocol/flutter/ble && flutter test               # Dart tests

python examples/image-projection/main.py --simulate   # project pictures, no hardware
python examples/basic-projection/main.py --address <BLE address>
```

To let an agent drive the device, see [mcp/irisgreen-mcp-server](mcp/irisgreen-mcp-server/README.md).
