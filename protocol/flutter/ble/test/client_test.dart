import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:irisgreen_ble/gatt_profile.dart' as g;
import 'package:irisgreen_ble/irisgreen_ble.dart';
import 'package:irisgreen_ble/protocol.dart' as p;

class FakeTransport implements Transport {
  FakeTransport({this.mtuValue = 512, this.reply});

  final int mtuValue;
  final List<List<int>> Function(List<int> frame)? reply;
  final writes = <(String, List<int>, bool)>[];
  final callbacks = <String, NotifyCallback>{};
  final reads = <String, Uint8List>{};

  @override
  Future<void> connect() async {}

  @override
  Future<void> disconnect() async {}

  @override
  int get mtu => mtuValue;

  @override
  Future<void> write(String uuid, List<int> data, {required bool response}) async {
    writes.add((uuid, List<int>.of(data), response));
    if (uuid == g.charMainCmd && reply != null) {
      for (final frame in reply!(data)) {
        callbacks[uuid]!(frame);
      }
    }
  }

  @override
  Future<Uint8List> read(String uuid) async {
    final v = reads[uuid];
    if (v == null) throw StateError('no $uuid');
    return v;
  }

  @override
  Future<void> startNotify(String uuid, NotifyCallback callback) async {
    callbacks[uuid] = callback;
  }

  @override
  Future<void> stopNotify(String uuid) async {
    callbacks.remove(uuid);
  }
}

IrisClient fast(FakeTransport t) => IrisClient(t)
  ..startDelay = Duration.zero
  ..packetDelay = Duration.zero;

void main() {
  test('command response skips status frames', () async {
    final status = [0x00, 0x00, 0x01, 0x22, 0x00, 0x00, 0x0F, 0x00];
    final t = FakeTransport(reply: (f) => [status, [0x80, f[0], 1, 55]]);
    final r = await IrisClient(t).sendCommand(p.buildRead(p.cmdBrightness));
    expect(r.ok, isTrue);
    expect(r.data, [55]);
    expect(t.callbacks, isEmpty);
    expect(t.writes.single.$1, g.charMainCmd);
    expect(t.writes.single.$3, isTrue);
  });

  test('timeout and mismatched reply', () async {
    var t = FakeTransport(reply: (f) => []);
    var r = await IrisClient(t)
        .sendCommand([0x11, 0], timeout: const Duration(milliseconds: 50));
    expect(r.ok, isFalse);
    expect(r.error, contains('timeout'));

    t = FakeTransport(reply: (f) => [[0x80, 0x99, 1, 0]]);
    r = await IrisClient(t)
        .sendCommand([0x11, 0], timeout: const Duration(milliseconds: 50));
    expect(r.ok, isFalse);
    expect(r.error, contains('no matching cmd'));
  });

  test('getPictureCount', () async {
    final t = FakeTransport(reply: (f) => [[0x80, f[0], 2, 0x2C, 0x01]]);
    expect(await IrisClient(t).getPictureCount(), 300);
  });

  test('pushFile sends start, chunked data, end', () async {
    final stream = Uint8List.fromList(
        [for (var i = 0; i < 1024; i++) i & 0xFF]);
    final t = FakeTransport(mtuValue: 203); // 200-byte chunks
    await fast(t).pushFile(stream, '1_1.bmp');

    final packet = p.buildFilePacket(stream.length, '1_1.bmp');
    expect(t.writes.first.$1, g.charFileStart);
    expect(t.writes.first.$2, packet);
    expect(t.writes.first.$3, isTrue);
    expect(t.writes.last.$1, g.charFileEnd);
    expect(t.writes.last.$2, packet);

    final data = t.writes.where((w) => w.$1 == g.charFileData).toList();
    expect(data.map((w) => w.$2.length), [200, 200, 200, 200, 200, 24]);
    expect(data.every((w) => w.$3 == false), isTrue);
    expect(data.expand((w) => w.$2).toList(), stream);
  });

  test('pushFile falls back to the minimum MTU', () async {
    final t = FakeTransport(mtuValue: 0);
    await fast(t).pushFile(Uint8List(45), 'a.bmp');
    final sizes =
        t.writes.where((w) => w.$1 == g.charFileData).map((w) => w.$2.length);
    expect(sizes, [20, 20, 5]);
  });

  test('loadInfo tolerates missing characteristics', () async {
    final t = FakeTransport()
      ..reads[g.charModelNumber] = Uint8List.fromList('IrisGreen'.codeUnits)
      ..reads[g.charBatteryLevel] = Uint8List.fromList([0xD2, 0x04, 0, 0]);
    final info = await IrisClient(t).loadInfo();
    expect(info.model, 'IrisGreen');
    expect(info.serial, '');
    expect(info.batteryU32, 1234);
  });

  test('connect records the MTU', () async {
    final c = IrisClient(FakeTransport(mtuValue: 247));
    await c.connect();
    expect(c.info.mtu, 247);
  });

  test('isIrisProjector', () {
    expect(g.isIrisProjector('Iris-G-B6B7CA'), isTrue);
    expect(g.isIrisProjector(null, [g.svcMain.toUpperCase()]), isTrue);
    expect(g.isIrisProjector('Other', ['0000180f-0000-1000-8000-00805f9b34fb']),
        isFalse);
  });
}
