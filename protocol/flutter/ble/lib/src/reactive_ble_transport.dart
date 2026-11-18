/// flutter_reactive_ble (BSD-3) implementation of [Transport] for Android and iOS.
library;

import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_reactive_ble/flutter_reactive_ble.dart';

import 'gatt_profile.dart' as g;
import 'transport.dart';

/// Scan for IrisGreen devices for [timeout] and return them, strongest signal first.
Future<List<DiscoveredDevice>> scanForIris(
  FlutterReactiveBle ble, {
  Duration timeout = const Duration(seconds: 8),
}) async {
  final found = <String, DiscoveredDevice>{};
  final sub = ble
      .scanForDevices(withServices: [Uuid.parse(g.advServiceUuid)])
      .listen((d) => found[d.id] = d);
  await Future<void>.delayed(timeout);
  await sub.cancel();
  return found.values.toList()..sort((a, b) => b.rssi.compareTo(a.rssi));
}

class ReactiveBleTransport implements Transport {
  ReactiveBleTransport(this.ble, this.deviceId);

  final FlutterReactiveBle ble;

  /// Platform device id: MAC address on Android, UUID on iOS.
  final String deviceId;

  final Map<String, Uuid> _serviceOf = {};
  StreamSubscription<ConnectionStateUpdate>? _connection;
  final Map<String, StreamSubscription<List<int>>> _subs = {};
  int _mtu = 0;

  @override
  int get mtu => _mtu;

  @override
  Future<void> connect() async {
    final connected = Completer<void>();
    _connection = ble
        .connectToDevice(
          id: deviceId,
          connectionTimeout: const Duration(seconds: 60),
        )
        .listen(
      (update) {
        if (update.connectionState == DeviceConnectionState.connected &&
            !connected.isCompleted) {
          connected.complete();
        } else if (update.connectionState == DeviceConnectionState.disconnected &&
            !connected.isCompleted) {
          connected.completeError(
            update.failure ?? StateError('disconnected before connecting'),
          );
        }
      },
      onError: (Object e) {
        if (!connected.isCompleted) connected.completeError(e);
      },
    );
    await connected.future;

    // Android defaults to ATT MTU 23. Request the device's 512; the call
    // returns the negotiated value (iOS negotiates by itself).
    try {
      _mtu = await ble.requestMtu(deviceId: deviceId, mtu: g.negotiatedMtu);
    } catch (_) {
      _mtu = 0;
    }

    _serviceOf.clear();
    await ble.discoverAllServices(deviceId);
    for (final s in await ble.getDiscoveredServices(deviceId)) {
      for (final c in s.characteristics) {
        _serviceOf[c.id.expanded.toString()] = s.id;
      }
    }
  }

  @override
  Future<void> disconnect() async {
    for (final sub in _subs.values) {
      await sub.cancel();
    }
    _subs.clear();
    await _connection?.cancel();
    _connection = null;
  }

  QualifiedCharacteristic _char(String uuid) {
    final id = Uuid.parse(uuid);
    final service = _serviceOf[id.expanded.toString()];
    if (service == null) throw StateError('characteristic $uuid not found');
    return QualifiedCharacteristic(
      characteristicId: id,
      serviceId: service,
      deviceId: deviceId,
    );
  }

  @override
  Future<void> write(
    String uuid,
    List<int> data, {
    required bool response,
  }) =>
      response
          ? ble.writeCharacteristicWithResponse(_char(uuid), value: data)
          : ble.writeCharacteristicWithoutResponse(_char(uuid), value: data);

  @override
  Future<Uint8List> read(String uuid) async =>
      Uint8List.fromList(await ble.readCharacteristic(_char(uuid)));

  @override
  Future<void> startNotify(String uuid, NotifyCallback callback) async {
    await _subs.remove(uuid)?.cancel();
    _subs[uuid] = ble.subscribeToCharacteristic(_char(uuid)).listen(callback);
  }

  @override
  Future<void> stopNotify(String uuid) async {
    await _subs.remove(uuid)?.cancel();
  }
}
