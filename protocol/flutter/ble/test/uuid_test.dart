import 'package:flutter_reactive_ble/flutter_reactive_ble.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:irisgreen_ble/gatt_profile.dart' as g;

void main() {
  // The transport keys characteristics by the expanded Uuid string; a short-form
  // id reported by the platform must match our full-form constants.
  test('expanded Uuid string is stable across short and full form', () {
    expect(
      Uuid.parse('2a19').expanded.toString(),
      Uuid.parse(g.charBatteryLevel).expanded.toString(),
    );
    expect(
      Uuid.parse(g.charMainCmd.toUpperCase()).expanded.toString(),
      Uuid.parse(g.charMainCmd).expanded.toString(),
    );
  });
}
