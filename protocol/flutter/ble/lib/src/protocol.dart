/// IrisGreen Bluetooth command protocol (V1.9). See docs/protocol-spec.md.
library;

import 'dart:convert';
import 'dart:typed_data';

const int cmdPicCount = 0x05;
const int cmdBrightness = 0x11;
const int cmdFlip = 0x12;
const int cmdKeystoneMode = 0x1C;
const int cmdKeystoneAngle = 0x1D;
const int cmdMirror = 0x1E;
const int cmdFov = 0x1F;
const int cmdPlay = 0xA0;
const int cmdPlayStop = 0xA1;
const int cmdDeletePic = 0xA2;

const int fileNameFieldMinBytes = 16;

/// type + len + data. [len] == 0 means "read".
Uint8List buildWrite(int cmd, [List<int> data = const []]) {
  if (data.length > 255) {
    throw ArgumentError('data too long: ${data.length} > 255');
  }
  return Uint8List.fromList([cmd & 0xFF, data.length, ...data]);
}

Uint8List buildRead(int cmd) => Uint8List.fromList([cmd & 0xFF, 0]);

class Response {
  const Response({
    required this.ok,
    this.cmd = 0,
    this.data = const [],
    this.raw = const [],
    this.error = '',
  });

  final bool ok;
  final int cmd;
  final List<int> data;
  final List<int> raw;
  final String error;

  int? get u16Le => data.length >= 2 ? data[0] | (data[1] << 8) : null;

  int? get u32Le => data.length >= 4
      ? data[0] | (data[1] << 8) | (data[2] << 16) | (data[3] << 24)
      : null;
}

/// Unsolicited 8-byte status frame (`00 00 01 .. .. .. .. 00`).
bool isStatusFrame(List<int> raw) =>
    raw.length == 8 &&
    raw[0] == 0x00 &&
    raw[1] == 0x00 &&
    raw[2] == 0x01 &&
    raw[7] == 0x00;

Response parseResponse(List<int> raw) {
  if (raw.length < 3) {
    return Response(ok: false, raw: raw, error: 'response too short');
  }
  if (isStatusFrame(raw)) {
    return Response(
      ok: false,
      raw: raw,
      error: 'status frame (not a command response)',
    );
  }
  if (raw[0] == 0x80 || raw[0] == 0x08) {
    final end = (3 + raw[2]).clamp(3, raw.length);
    return Response(ok: true, cmd: raw[1], data: raw.sublist(3, end), raw: raw);
  }
  return Response(
    ok: false,
    raw: raw,
    error: 'unknown frame format, first byte=0x${raw[0].toRadixString(16)}',
  );
}

Uint8List cmdSetKeystone(int mode) {
  if (mode < 0 || mode > 3) throw ArgumentError('mode must be 0..3');
  return buildWrite(cmdKeystoneMode, [mode]);
}

/// Angle -70..70. Negatives are encoded as `70 + abs(angle)`.
Uint8List cmdSetKeystoneAngle(int angle) {
  if (angle < -70 || angle > 70) {
    throw ArgumentError('angle must be in -70..70');
  }
  return buildWrite(cmdKeystoneAngle, [angle >= 0 ? angle : 70 + angle.abs()]);
}

/// Inverse of the angle encoding: a value above 70 is a negative angle.
int decodeKeystoneAngle(int value) => value <= 70 ? value : -(value - 70);

Uint8List cmdSetFov(int level) {
  if (level < 0 || level > 2) throw ArgumentError('level must be 0..2');
  return buildWrite(cmdFov, [level]);
}

Uint8List cmdSetBrightness(int percent) {
  if (percent < 0 || percent > 100) {
    throw ArgumentError('brightness must be in 0..100');
  }
  return buildWrite(cmdBrightness, [percent]);
}

Uint8List cmdSetMirror(bool enable) => buildWrite(cmdMirror, [enable ? 1 : 0]);

Uint8List cmdSetFlip(bool upsideDown) =>
    buildWrite(cmdFlip, [upsideDown ? 1 : 0]);

Uint8List cmdPlayGroup(
  int groupId, {
  bool loop = false,
  int total100ms = 100,
  int interval100ms = 2,
}) {
  if (groupId < 0 || groupId > 0xFF) {
    throw ArgumentError('group_id out of range');
  }
  if (total100ms > 36000) {
    throw ArgumentError('total play time cap is 1 hour (36000 * 100ms)');
  }
  return buildWrite(cmdPlay, [
    loop ? 1 : 0,
    total100ms & 0xFF,
    (total100ms >> 8) & 0xFF,
    interval100ms & 0xFF,
    (interval100ms >> 8) & 0xFF,
    groupId,
  ]);
}

Uint8List cmdPlayStopFrame() => buildWrite(cmdPlayStop, [1]);

Uint8List cmdDeleteGroup(int groupId) =>
    buildWrite(cmdDeletePic, [groupId & 0xFF]);

/// Start/end packet of a file transfer:
/// size (u32 big-endian) + name (UTF-8, NUL padded to at least 16 bytes).
Uint8List buildFilePacket(int fileSize, String fileName) {
  final name = utf8.encode(fileName);
  final field = name.length < fileNameFieldMinBytes
      ? fileNameFieldMinBytes
      : name.length;
  final out = Uint8List(4 + field);
  out[0] = (fileSize >> 24) & 0xFF;
  out[1] = (fileSize >> 16) & 0xFF;
  out[2] = (fileSize >> 8) & 0xFF;
  out[3] = fileSize & 0xFF;
  out.setRange(4, 4 + name.length, name);
  return out;
}
