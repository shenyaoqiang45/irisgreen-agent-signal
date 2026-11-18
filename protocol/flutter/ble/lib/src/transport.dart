/// Platform BLE abstraction: the SDK speaks IrisGreen on top of this.
library;

import 'dart:typed_data';

typedef NotifyCallback = void Function(List<int> data);

abstract class Transport {
  Future<void> connect();

  Future<void> disconnect();

  /// Negotiated ATT MTU, or 0 if unknown.
  int get mtu;

  Future<void> write(String uuid, List<int> data, {required bool response});

  Future<Uint8List> read(String uuid);

  /// Subscribe to notifications or indications on a characteristic.
  Future<void> startNotify(String uuid, NotifyCallback callback);

  Future<void> stopNotify(String uuid);
}
