/// 640x480 1bpp image packing for the IrisGreen data stream.
///
/// Must produce byte-identical output to the Python SDK `image_pack.pack`.
library;

import 'dart:typed_data';

const int width = 640;
const int height = 480;
const int rowBytes = width ~/ 8; // 80
const int dataBytes = rowBytes * height; // 38400
const int headBytes = 62;
const int streamBytes = headBytes + dataBytes; // 38462

/// 62-byte BMP header (640x480, 1bpp, data offset 62).
final Uint8List bmpHead = Uint8List.fromList(const [
  0x42, 0x4D, 0x3E, 0x96, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x3E, 0x00, //
  0x00, 0x00, 0x28, 0x00, 0x00, 0x00, 0x80, 0x02, 0x00, 0x00, 0xE0, 0x01,
  0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x96,
  0x00, 0x00, 0x12, 0x0B, 0x00, 0x00, 0x12, 0x0B, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF,
  0xFF, 0x00,
]);

/// Binary image (row-major, [height] rows of [width] values, non-zero = lit)
/// -> 38400-byte payload, rotated 180 degrees, MSB first.
Uint8List pack(List<int> bw) {
  if (bw.length != width * height) {
    throw ArgumentError('expected ${width * height} pixels, got ${bw.length}');
  }
  final out = Uint8List(dataBytes);
  final last = width * height - 1;
  for (var i = 0; i < bw.length; i++) {
    if (bw[last - i] != 0) {
      out[i >> 3] |= 0x80 >> (i & 7);
    }
  }
  return out;
}

/// 62-byte header + 38400-byte payload = 38462 bytes.
Uint8List buildStream(List<int> bw) {
  final out = Uint8List(streamBytes);
  out.setRange(0, headBytes, bmpHead);
  out.setRange(headBytes, streamBytes, pack(bw));
  return out;
}
