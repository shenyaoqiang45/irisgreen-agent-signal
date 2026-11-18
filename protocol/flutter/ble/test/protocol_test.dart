import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:irisgreen_ble/image_pack.dart' as img;
import 'package:irisgreen_ble/protocol.dart' as p;

Uint8List hex(String s) => Uint8List.fromList([
      for (var i = 0; i < s.length; i += 2)
        int.parse(s.substring(i, i + 2), radix: 16),
    ]);

String toHex(List<int> b) =>
    b.map((x) => x.toRadixString(16).padLeft(2, '0')).join().toUpperCase();

final vectors = jsonDecode(
  File('../../../tests/cross-platform/protocol-vectors.json').readAsStringSync(),
) as Map<String, dynamic>;

final builders = <String, Uint8List Function()>{
  'read brightness': () => p.buildRead(p.cmdBrightness),
  'set brightness 100': () => p.cmdSetBrightness(100),
  'read picture count': () => p.buildRead(p.cmdPicCount),
  'set keystone mode 2': () => p.cmdSetKeystone(2),
  'set keystone angle 10': () => p.cmdSetKeystoneAngle(10),
  'set keystone angle -10': () => p.cmdSetKeystoneAngle(-10),
  'set keystone angle -70': () => p.cmdSetKeystoneAngle(-70),
  'set fov 1': () => p.cmdSetFov(1),
  'mirror on': () => p.cmdSetMirror(true),
  'flip upside down': () => p.cmdSetFlip(true),
  'play group 0x0B (spec example)': () => p.cmdPlayGroup(0x0B),
  'play stop': p.cmdPlayStopFrame,
  'delete group 5': () => p.cmdDeleteGroup(5),
};

void main() {
  test('every vector has a builder', () {
    final names = [for (final v in vectors['commands']) v['name'] as String];
    expect(names.toSet(), builders.keys.toSet());
  });

  group('command frames match golden vectors', () {
    for (final v in vectors['commands']) {
      test(v['name'], () {
        expect(toHex(builders[v['name']]!()), (v['frame'] as String).toUpperCase());
      });
    }
  });

  group('response parsing matches golden vectors', () {
    for (final v in vectors['responses']) {
      test(v['name'], () {
        final r = p.parseResponse(hex(v['raw']));
        expect(r.ok, v['ok']);
        if (v['ok'] == true) {
          expect(r.cmd, v['cmd']);
          expect(toHex(r.data), (v['data'] as String).toUpperCase());
        }
      });
    }
  });

  group('file packets match golden vectors', () {
    for (final v in vectors['file_packets']) {
      test(v['name'], () {
        final packet = p.buildFilePacket(v['size'], v['file_name']);
        expect(toHex(packet), (v['packet'] as String).toUpperCase());
      });
    }
  });

  test('response accessors', () {
    final r = p.parseResponse(hex('8005022C01'));
    expect(r.u16Le, 300);
  });

  test('validation', () {
    expect(() => p.cmdSetBrightness(101), throwsArgumentError);
    expect(() => p.cmdSetKeystoneAngle(71), throwsArgumentError);
    expect(() => p.cmdPlayGroup(1, total100ms: 36001), throwsArgumentError);
    expect(() => p.buildWrite(0xA6, List.filled(256, 0)), throwsArgumentError);
  });

  group('image packing', () {
    test('sizes and header match the Python SDK', () {
      expect(img.bmpHead.length, img.headBytes);
      expect(toHex(img.bmpHead), (vectors['image']['bmp_head'] as String).toUpperCase());
      final stream = img.buildStream(List.filled(img.width * img.height, 0));
      expect(stream.length, img.streamBytes);
    });

    for (final v in vectors['image']['pack']) {
      test(v['name'], () {
        final bw = List<int>.filled(img.width * img.height, 0);
        for (final px in v['pixels']) {
          bw[px[0] * img.width + px[1]] = 1;
        }
        final out = img.pack(bw);
        expect(out[v['byte_index']], int.parse(v['value'], radix: 16));
        expect(out.fold<int>(0, (a, b) => a + b), int.parse(v['value'], radix: 16));
      });
    }

    test('rejects wrong size', () {
      expect(() => img.pack([1, 2, 3]), throwsArgumentError);
    });
  });
}
