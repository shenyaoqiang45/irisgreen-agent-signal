/// IrisGreen BLE Protocol SDK client (V0.2): commands and image transfer.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'gatt_profile.dart' as g;
import 'protocol.dart' as p;
import 'transport.dart';

const Duration writeTimeout = Duration(seconds: 15);
const int defaultAttMtu = 23;

class DeviceInfo {
  String address;
  String model = '';
  String serial = '';
  String firmware = '';
  String manufacturer = '';
  List<int> batteryRaw = const [];
  int mtu = 0;

  DeviceInfo(this.address);

  /// Raw battery value. The device returns 4 bytes (non-standard); units unconfirmed.
  int? get batteryU32 {
    if (batteryRaw.length >= 4) {
      return batteryRaw[0] |
          (batteryRaw[1] << 8) |
          (batteryRaw[2] << 16) |
          (batteryRaw[3] << 24);
    }
    return batteryRaw.isNotEmpty ? batteryRaw[0] : null;
  }
}

class IrisClient {
  IrisClient(this.transport, {String address = ''})
      : info = DeviceInfo(address);

  final Transport transport;
  final DeviceInfo info;

  /// Delays between file-transfer steps; tests set these to zero.
  Duration startDelay = const Duration(milliseconds: 100);
  Duration packetDelay = const Duration(milliseconds: 30);

  Future<void> connect() async {
    await transport.connect();
    info.mtu = transport.mtu;
  }

  Future<void> disconnect() => transport.disconnect();

  /// Write a command frame; the response arrives as an indication on the
  /// same characteristic.
  Future<p.Response> sendCommand(
    List<int> frame, {
    bool waitResponse = true,
    Duration timeout = writeTimeout,
  }) async {
    if (!waitResponse) {
      await transport.write(g.charMainCmd, frame, response: true);
      return p.Response(ok: true, raw: frame);
    }

    final got = <List<int>>[];
    final match = Completer<p.Response>();
    await transport.startNotify(g.charMainCmd, (data) {
      got.add(List<int>.of(data));
      final resp = p.parseResponse(data);
      if (resp.ok && resp.cmd == frame[0] && !match.isCompleted) {
        match.complete(resp);
      }
    });
    try {
      await transport.write(g.charMainCmd, frame, response: true);
      return await match.future.timeout(timeout);
    } on TimeoutException {
      if (got.isNotEmpty) {
        return p.Response(
          ok: false,
          raw: got.last,
          error: 'no matching cmd=0x${frame[0].toRadixString(16)}, '
              'received ${got.length} frame(s)',
        );
      }
      return const p.Response(ok: false, error: 'timeout, no response');
    } finally {
      try {
        await transport.stopNotify(g.charMainCmd);
      } catch (_) {}
    }
  }

  Future<String> _readString(String uuid) async {
    try {
      return ascii.decode(await transport.read(uuid), allowInvalid: true);
    } catch (_) {
      return '';
    }
  }

  Future<DeviceInfo> loadInfo() async {
    info.model = await _readString(g.charModelNumber);
    info.serial = await _readString(g.charSerialNumber);
    info.firmware = await _readString(g.charFirmwareRev);
    info.manufacturer = await _readString(g.charManufacturer);
    try {
      info.batteryRaw = await transport.read(g.charBatteryLevel);
    } catch (_) {
      info.batteryRaw = const [];
    }
    return info;
  }

  /// Upload a file (e.g. a 38462-byte 1bpp stream) via the file-transfer service.
  Future<void> pushFile(Uint8List stream, String name) async {
    final packet = p.buildFilePacket(stream.length, name);
    await transport.write(g.charFileStart, packet, response: true);
    await Future<void>.delayed(startDelay);

    final mtu = transport.mtu == 0 ? defaultAttMtu : transport.mtu;
    final size = (mtu - g.attOverhead).clamp(1, 1 << 20);
    for (var i = 0; i < stream.length; i += size) {
      final end = (i + size).clamp(0, stream.length);
      await transport.write(
        g.charFileData,
        Uint8List.sublistView(stream, i, end),
        response: false,
      );
      await Future<void>.delayed(packetDelay);
    }
    await transport.write(g.charFileEnd, packet, response: true);
  }

  Future<int?> getPictureCount() async {
    final r = await sendCommand(p.buildRead(p.cmdPicCount));
    return r.ok ? r.u16Le : null;
  }

  Future<int?> getBrightness() async {
    final r = await sendCommand(p.buildRead(p.cmdBrightness));
    return r.ok && r.data.isNotEmpty ? r.data[0] : null;
  }

  Future<p.Response> setBrightness(int percent) =>
      sendCommand(p.cmdSetBrightness(percent));

  Future<p.Response> setKeystoneMode(int mode) =>
      sendCommand(p.cmdSetKeystone(mode));

  Future<int?> getKeystoneAngle() async {
    final r = await sendCommand(p.buildRead(p.cmdKeystoneAngle));
    return r.ok && r.data.isNotEmpty ? p.decodeKeystoneAngle(r.data[0]) : null;
  }

  Future<p.Response> setKeystoneAngle(int angle) =>
      sendCommand(p.cmdSetKeystoneAngle(angle));

  Future<int?> getFov() async {
    final r = await sendCommand(p.buildRead(p.cmdFov));
    return r.ok && r.data.isNotEmpty ? r.data[0] : null;
  }

  Future<p.Response> setFov(int level) => sendCommand(p.cmdSetFov(level));

  Future<bool?> getMirror() async {
    final r = await sendCommand(p.buildRead(p.cmdMirror));
    return r.ok && r.data.isNotEmpty ? r.data[0] != 0 : null;
  }

  Future<p.Response> setMirror(bool enable) =>
      sendCommand(p.cmdSetMirror(enable));

  Future<bool?> getFlip() async {
    final r = await sendCommand(p.buildRead(p.cmdFlip));
    return r.ok && r.data.isNotEmpty ? r.data[0] != 0 : null;
  }

  Future<p.Response> setFlip(bool upsideDown) =>
      sendCommand(p.cmdSetFlip(upsideDown));

  Future<p.Response> play(
    int groupId, {
    bool loop = false,
    int total100ms = 100,
    int interval100ms = 2,
  }) =>
      sendCommand(p.cmdPlayGroup(
        groupId,
        loop: loop,
        total100ms: total100ms,
        interval100ms: interval100ms,
      ));

  Future<p.Response> stop() => sendCommand(p.cmdPlayStopFrame());
}
