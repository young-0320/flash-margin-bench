/*
 * TMP117 Step B standalone test
 *
 * Wiring (Arduino Uno/Nano):
 *   TMP117 VCC  -> Arduino 3.3V
 *   TMP117 GND  -> Arduino GND
 *   TMP117 SDA  -> Arduino SDA (Uno/Nano: A4)
 *   TMP117 SCL  -> Arduino SCL (Uno/Nano: A5)
 *
 * If the sensor board has no I2C pull-up resistors, add:
 *   SDA -> 4.7 kOhm -> 3.3V
 *   SCL -> 4.7 kOhm -> 3.3V
 *
 * The sketch scans all four valid TMP117 addresses (0x48 to 0x4B),
 * verifies the device ID register, and reads the temperature register.
 * No external Arduino library is required; only the built-in Wire library.
 */

#include <Wire.h>

constexpr uint8_t TMP117_TEMP_REGISTER = 0x00;
constexpr uint8_t TMP117_DEVICE_ID_REGISTER = 0x0F;
constexpr uint16_t TMP117_DEVICE_ID = 0x0117;
constexpr unsigned long READ_INTERVAL_MS = 1000;

uint8_t tmp117Address = 0;
unsigned long lastReadMs = 0;

bool deviceResponds(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

bool readRegister16(uint8_t address, uint8_t registerAddress,
                    uint16_t &value) {
  Wire.beginTransmission(address);
  Wire.write(registerAddress);

  // false keeps control of the bus for the repeated-start read operation.
  if (Wire.endTransmission(false) != 0) {
    return false;
  }

  const uint8_t bytesRead = Wire.requestFrom(address, (uint8_t)2);
  if (bytesRead != 2 || Wire.available() < 2) {
    return false;
  }

  const uint8_t msb = Wire.read();
  const uint8_t lsb = Wire.read();
  value = ((uint16_t)msb << 8) | lsb;
  return true;
}

void printHexByte(uint8_t value) {
  if (value < 0x10) {
    Serial.print('0');
  }
  Serial.print(value, HEX);
}

void scanI2CBus() {
  Serial.println(F("I2C bus scan:"));
  uint8_t count = 0;

  for (uint8_t address = 1; address < 0x7F; ++address) {
    if (deviceResponds(address)) {
      Serial.print(F("  device found at 0x"));
      printHexByte(address);
      Serial.println();
      ++count;
    }
  }

  if (count == 0) {
    Serial.println(F("  no I2C device found"));
  }
}

uint8_t findTmp117() {
  for (uint8_t address = 0x48; address <= 0x4B; ++address) {
    if (!deviceResponds(address)) {
      continue;
    }

    uint16_t deviceId = 0;
    if (!readRegister16(address, TMP117_DEVICE_ID_REGISTER, deviceId)) {
      continue;
    }

    // Bits 11:0 contain 0x117. Bits 15:12 contain the silicon revision.
    if ((deviceId & 0x0FFF) == TMP117_DEVICE_ID) {
      Serial.print(F("TMP117 verified at 0x"));
      printHexByte(address);
      Serial.print(F(", device ID = 0x"));
      if (deviceId < 0x1000) {
        Serial.print('0');
      }
      Serial.println(deviceId, HEX);
      return address;
    }

    Serial.print(F("Device at 0x"));
    printHexByte(address);
    Serial.print(F(" has a non-TMP117 device ID: 0x"));
    if (deviceId < 0x1000) {
      Serial.print('0');
    }
    Serial.println(deviceId, HEX);
  }

  return 0;
}

void reportSafeError() {
  Serial.println(F("[ERROR] TMP117 not found or I2C read failed."));
  Serial.println(F("Check 3.3V, GND, SDA, SCL, and both 4.7 kOhm pull-ups."));
  Serial.println(F("SAFE STATE: no heater command is issued."));
}

void setup() {
  Serial.begin(115200);

  // Native-USB boards can wait briefly for the Serial Monitor. Uno/Nano do
  // not need this, and the timeout prevents an indefinite startup wait.
  const unsigned long serialWaitStart = millis();
  while (!Serial && millis() - serialWaitStart < 2000) {
  }

  Wire.begin();
  Wire.setClock(100000);

  Serial.println();
  Serial.println(F("=== TMP117 Step B standalone test ==="));
  scanI2CBus();
  tmp117Address = findTmp117();

  if (tmp117Address == 0) {
    reportSafeError();
  } else {
    Serial.println(F("Touch the small TMP117 IC at the probe tip and watch the value rise."));
  }
}

void loop() {
  if (millis() - lastReadMs < READ_INTERVAL_MS) {
    return;
  }
  lastReadMs = millis();

  if (tmp117Address == 0) {
    tmp117Address = findTmp117();
    if (tmp117Address == 0) {
      reportSafeError();
      return;
    }
  }

  uint16_t rawUnsigned = 0;
  if (!readRegister16(tmp117Address, TMP117_TEMP_REGISTER, rawUnsigned)) {
    tmp117Address = 0;
    reportSafeError();
    return;
  }

  // Immediately after power-up, 0x8000 means the first averaged conversion
  // has not finished yet. It is not a real -256 C measurement.
  if (rawUnsigned == 0x8000) {
    Serial.println(F("TMP117 is completing its first conversion; wait for the next line."));
    return;
  }

  // TMP117 temperature is a signed 16-bit two's-complement value.
  const int16_t rawSigned = (int16_t)rawUnsigned;
  const float temperatureC = rawSigned / 128.0f;

  Serial.print(F("address=0x"));
  printHexByte(tmp117Address);
  Serial.print(F("  register=0x00  raw=0x"));
  if (rawUnsigned < 0x1000) {
    Serial.print('0');
  }
  if (rawUnsigned < 0x0100) {
    Serial.print('0');
  }
  if (rawUnsigned < 0x0010) {
    Serial.print('0');
  }
  Serial.print(rawUnsigned, HEX);
  Serial.print(F("  temperature="));
  Serial.print(temperatureC, 3);
  Serial.println(F(" C"));
}
