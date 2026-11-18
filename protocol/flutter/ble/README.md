# irisgreen_ble (Flutter)

IrisGreen BLE Protocol SDK for Android and iOS (roadmap V0.1 / V0.2). It is the Dart twin of [sdk/ble-protocol-sdk](../../../sdk/ble-protocol-sdk) and is held to the same golden vectors in [tests/cross-platform](../../../tests/cross-platform/protocol-vectors.json).

| Library | Role |
|---|---|
| `gatt_profile.dart` | GATT UUIDs and link limits |
| `protocol.dart` | Command frames, response parsing, file packets |
| `image_pack.dart` | 640x480 1bpp payload packing |
| `irisgreen_ble.dart` | `Transport`, `IrisClient`, `ReactiveBleTransport` |

```dart
final ble = FlutterReactiveBle();
final devices = await scanForIris(ble);
final client = IrisClient(ReactiveBleTransport(ble, devices.first.id));

await client.connect();
await client.loadInfo();
await client.setBrightness(80);
await client.pushFile(buildStream(bw), '1_1.bmp'); // bw: 640x480, non-zero = lit
await client.play(1);
await client.disconnect();
```

The transport uses [flutter_reactive_ble](https://pub.dev/packages/flutter_reactive_ble) (BSD-3). `flutter_blue_plus` 2.x was rejected because it needs a paid license for commercial use.

## Platform setup

- Android: declare `BLUETOOTH_SCAN` (with `neverForLocation`) and `BLUETOOTH_CONNECT` in the manifest and request them at runtime. Android 11 and below need `ACCESS_FINE_LOCATION`. The transport requests MTU 512 after connecting.
- iOS: add `NSBluetoothAlwaysUsageDescription` to `Info.plist`. iOS negotiates the MTU itself.

## Tests

```text
flutter test
flutter analyze
```

The tests use an in-memory `Transport`. Verifying real connections on Android and iOS hardware is the V0.1 / V0.2 acceptance and is still to be done.
