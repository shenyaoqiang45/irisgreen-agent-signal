/// IrisGreen GATT profile (V0.1): the BLE contract the device exposes.
///
/// Mirrors protocol/gatt/specification/irisgreen-gatt.json and the Python SDK.
library;

// Primary custom service (commands / image stream).
const String svcMain = 'adb401c0-b1c6-11ed-afa1-0242ac120002';

const String charMainStatusRead = 'adb40001-b1c6-11ed-afa1-0242ac120001';
const String charMainNotify = 'adb40002-b1c6-11ed-afa1-0242ac120002';
const String charMainCmd = 'adb40003-b1c6-11ed-afa1-0242ac120003';
const String charMainData = 'adb40004-b1c6-11ed-afa1-0242ac120004';
const String charMainCmd2 = 'adb40005-b1c6-11ed-afa1-0242ac120005';

// Secondary custom service (file transfer). Map by UUID suffix, not by the
// order in the protocol spreadsheet.
const String svcSecondary = 'adb40006-b1c6-11ed-afa1-0242ac120001';

const String charFileStart = 'adb40006-b1c6-11ed-afa1-0242ac120003';
const String charFileData = 'adb40006-b1c6-11ed-afa1-0242ac120002';
const String charFileEnd = 'adb40006-b1c6-11ed-afa1-0242ac120004';

// Standard characteristics.
const String charDeviceName = '00002a00-0000-1000-8000-00805f9b34fb';
const String charBatteryLevel = '00002a19-0000-1000-8000-00805f9b34fb';
const String charModelNumber = '00002a24-0000-1000-8000-00805f9b34fb';
const String charSerialNumber = '00002a25-0000-1000-8000-00805f9b34fb';
const String charFirmwareRev = '00002a26-0000-1000-8000-00805f9b34fb';
const String charManufacturer = '00002a29-0000-1000-8000-00805f9b34fb';

const String advServiceUuid = svcMain;
const String namePrefix = 'Iris-G';

const int negotiatedMtu = 512;
const int attOverhead = 3;
const int maxChunk = negotiatedMtu - attOverhead; // 509

/// True if an advertisement looks like an IrisGreen projector.
bool isIrisProjector(String? name, [List<String>? serviceUuids]) {
  if (name != null && name.toLowerCase().contains(namePrefix.toLowerCase())) {
    return true;
  }
  if (serviceUuids != null) {
    return serviceUuids.any((u) => u.toLowerCase() == advServiceUuid);
  }
  return false;
}
