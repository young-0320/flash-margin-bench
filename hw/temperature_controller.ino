/*
 * TMP117 + DFR0457 temperature controller for Arduino Uno/Nano
 *
 * TMP117 (same wiring verified by tmp117_test.ino):
 *   VCC -> Arduino 3.3V
 *   GND -> Arduino GND
 *   SDA -> Arduino A4/SDA
 *   SCL -> Arduino A5/SCL
 *   Add 4.7 kOhm pull-ups from SDA and SCL to 3.3V if the module
 *   does not already include them.
 *
 * DFR0457 Gravity logic connector (follow the board labels):
 *   VCC -> Arduino 5V
 *   GND -> Arduino GND
 *   S   -> Arduino D9 (about 490 Hz PWM on Uno)
 *
 * DFR0457 power terminals (follow VIN/GND/VOUT silkscreen):
 *   VIN  -> bench supply +5.0V
 *   GND  -> bench supply 0V and heater lead 2
 *   VOUT -> heater lead 1
 *
 * The sketch starts DISARMED. Open Serial Monitor at 115200 baud.
 * Commands:
 *   T33      set 33 C and arm the heater
 *   T60      set 60 C and arm the heater
 *   T=45     set any target from 25 C to 60 C and arm
 *   OFF      heater off
 *   STATUS   print current state
 *   RESET    clear a latched fault below RESET_MAX_C; remains off
 *   HELP     print commands
 *
 * Safety behavior:
 *   - PWM is zero during reset/startup and whenever the controller is off.
 *   - Any TMP117/I2C error immediately latches the heater off.
 *   - Temperature >= ABSOLUTE_CUTOFF_C latches the heater off.
 *   - A run longer than MAX_RUN_MS latches the heater off.
 *   - Faults never auto-restart. RESET and a new Txx command are required.
 *
 * Software cutoff cannot protect against a shorted MOSFET, a crashed MCU,
 * a detached sensor that still reports a plausible value, or wiring faults.
 * Use the bench supply current limit and supervise the temporary no-fuse test.
 */

#include <Wire.h>
#include <ctype.h>
#include <stdlib.h>
#include <string.h>

constexpr uint8_t HEATER_PWM_PIN = 9;

constexpr uint8_t TMP117_TEMP_REGISTER = 0x00;
constexpr uint8_t TMP117_DEVICE_ID_REGISTER = 0x0F;
constexpr uint16_t TMP117_DEVICE_ID = 0x0117;

constexpr unsigned long CONTROL_INTERVAL_MS = 1000UL;
constexpr unsigned long MAX_RUN_MS = 20UL * 60UL * 1000UL;

constexpr float TARGET_MIN_C = 25.0f;
constexpr float TARGET_MAX_C = 60.0f;
constexpr float ABSOLUTE_CUTOFF_C = 50.0f;
constexpr float RESET_MAX_C = 32.0f;
constexpr float PLAUSIBLE_MIN_C = -20.0f;
constexpr float PLAUSIBLE_MAX_C = 100.0f;

// Conservative first-run values. 128/255 is about 50% maximum average power.
// Raise PWM_LIMIT only after a 33 C test has shown acceptable overshoot.
constexpr uint8_t PWM_LIMIT = 128;
constexpr uint8_t PWM_RISE_LIMIT_PER_STEP = 12;

// Starting PI gains. They must be tuned with the actual heater/plate/insulation.
constexpr float KP = 12.0f;  // PWM counts per degree C
constexpr float KI = 0.40f;  // PWM counts per degree C per second
constexpr float OVERSHOOT_OFF_C = 0.30f;

enum FaultCode : uint8_t {
  FAULT_NONE = 0,
  FAULT_SENSOR,
  FAULT_OVERTEMP,
  FAULT_RUN_TIMEOUT
};

uint8_t tmp117Address = 0;
bool sensorConversionPending = false;
bool heaterArmed = false;
FaultCode faultCode = FAULT_NONE;

float targetC = 33.0f;
float lastTemperatureC = 0.0f;
float integralTerm = 0.0f;
uint8_t currentPwm = 0;

unsigned long lastControlMs = 0;
unsigned long runStartedMs = 0;

char commandBuffer[32];
uint8_t commandLength = 0;

void heaterOff() {
  analogWrite(HEATER_PWM_PIN, 0);
  digitalWrite(HEATER_PWM_PIN, LOW);
  currentPwm = 0;
}

const __FlashStringHelper *faultName(FaultCode code) {
  switch (code) {
    case FAULT_SENSOR: return F("SENSOR");
    case FAULT_OVERTEMP: return F("OVERTEMP");
    case FAULT_RUN_TIMEOUT: return F("RUN_TIMEOUT");
    default: return F("NONE");
  }
}

void latchFault(FaultCode code) {
  heaterOff();
  heaterArmed = false;
  integralTerm = 0.0f;
  faultCode = code;

  Serial.print(F("FAULT_LATCHED,"));
  Serial.println(faultName(code));
}

bool deviceResponds(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

bool readRegister16(uint8_t address, uint8_t registerAddress,
                    uint16_t &value) {
  Wire.beginTransmission(address);
  Wire.write(registerAddress);
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

#if defined(WIRE_HAS_TIMEOUT)
  if (Wire.getWireTimeoutFlag()) {
    Wire.clearWireTimeoutFlag();
    return false;
  }
#endif

  return true;
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

    if ((deviceId & 0x0FFF) == TMP117_DEVICE_ID) {
      return address;
    }
  }
  return 0;
}

bool readTemperatureC(float &temperatureC) {
  sensorConversionPending = false;

  if (tmp117Address == 0) {
    tmp117Address = findTmp117();
    if (tmp117Address == 0) {
      return false;
    }
  }

  uint16_t rawUnsigned = 0;
  if (!readRegister16(tmp117Address, TMP117_TEMP_REGISTER, rawUnsigned)) {
    tmp117Address = 0;
    return false;
  }

  // TMP117 reports 0x8000 before the first valid conversion completes.
  if (rawUnsigned == 0x8000) {
    sensorConversionPending = true;
    return false;
  }

  const int16_t rawSigned = (int16_t)rawUnsigned;
  temperatureC = rawSigned / 128.0f;

  return temperatureC >= PLAUSIBLE_MIN_C &&
         temperatureC <= PLAUSIBLE_MAX_C;
}

void printHelp() {
  Serial.println(F("Commands: T33 | T=<25..60> | OFF | STATUS | RESET | HELP"));
}

void printStatus() {
  Serial.print(F("STATUS,state="));
  if (faultCode != FAULT_NONE) {
    Serial.print(F("FAULT"));
  } else if (heaterArmed) {
    Serial.print(F("RUN"));
  } else {
    Serial.print(F("OFF"));
  }
  Serial.print(F(",fault="));
  Serial.print(faultName(faultCode));
  Serial.print(F(",target_c="));
  Serial.print(targetC, 2);
  Serial.print(F(",temp_c="));
  Serial.print(lastTemperatureC, 3);
  Serial.print(F(",pwm="));
  Serial.println(currentPwm);
}

bool parseTarget(const char *command, float &value) {
  const char *number = nullptr;

  if (command[0] == 'T') {
    number = command + 1;
    if (*number == '=') {
      ++number;
    }
  } else if (strncmp(command, "SET ", 4) == 0) {
    number = command + 4;
  }

  if (number == nullptr || *number == '\0') {
    return false;
  }

  char *end = nullptr;
  value = (float)strtod(number, &end);
  return end != number && *end == '\0';
}

void armTarget(float requestedTargetC) {
  if (requestedTargetC < TARGET_MIN_C || requestedTargetC > TARGET_MAX_C) {
    Serial.println(F("REJECT,target must be 25.0..60.0 C"));
    return;
  }

  if (faultCode != FAULT_NONE) {
    Serial.println(F("REJECT,fault is latched; use RESET after cooling"));
    return;
  }

  float temperatureC = 0.0f;
  if (!readTemperatureC(temperatureC)) {
    if (sensorConversionPending) {
      Serial.println(F("REJECT,TMP117 first conversion is not ready"));
      return;
    }
    latchFault(FAULT_SENSOR);
    return;
  }

  lastTemperatureC = temperatureC;
  if (temperatureC >= ABSOLUTE_CUTOFF_C) {
    latchFault(FAULT_OVERTEMP);
    return;
  }

  heaterOff();
  integralTerm = 0.0f;
  targetC = requestedTargetC;
  heaterArmed = true;
  runStartedMs = millis();
  lastControlMs = millis();

  Serial.print(F("ARMED,target_c="));
  Serial.println(targetC, 2);
}

void resetFault() {
  heaterOff();
  heaterArmed = false;
  integralTerm = 0.0f;

  tmp117Address = findTmp117();
  float temperatureC = 0.0f;
  if (tmp117Address == 0 || !readTemperatureC(temperatureC)) {
    faultCode = FAULT_SENSOR;
    Serial.println(F("RESET_REJECTED,TMP117 unavailable"));
    return;
  }

  lastTemperatureC = temperatureC;
  if (temperatureC > RESET_MAX_C) {
    faultCode = FAULT_OVERTEMP;
    Serial.print(F("RESET_REJECTED,temp_c="));
    Serial.println(temperatureC, 3);
    return;
  }

  faultCode = FAULT_NONE;
  Serial.println(F("FAULT_CLEARED,heater remains OFF"));
}

void processCommand(char *command) {
  for (char *p = command; *p != '\0'; ++p) {
    *p = (char)toupper((unsigned char)*p);
  }

  if (strcmp(command, "OFF") == 0) {
    heaterOff();
    heaterArmed = false;
    integralTerm = 0.0f;
    Serial.println(F("HEATER_OFF"));
    return;
  }

  if (strcmp(command, "STATUS") == 0) {
    printStatus();
    return;
  }

  if (strcmp(command, "RESET") == 0) {
    resetFault();
    return;
  }

  if (strcmp(command, "HELP") == 0) {
    printHelp();
    return;
  }

  float requestedTargetC = 0.0f;
  if (parseTarget(command, requestedTargetC)) {
    armTarget(requestedTargetC);
    return;
  }

  Serial.println(F("REJECT,unknown command"));
  printHelp();
}

void serviceSerial() {
  while (Serial.available() > 0) {
    const char c = (char)Serial.read();

    if (c == '\r' || c == '\n') {
      if (commandLength > 0) {
        commandBuffer[commandLength] = '\0';
        processCommand(commandBuffer);
        commandLength = 0;
      }
      continue;
    }

    if (commandLength < sizeof(commandBuffer) - 1) {
      commandBuffer[commandLength++] = c;
    } else {
      commandLength = 0;
      Serial.println(F("REJECT,command too long"));
    }
  }
}

uint8_t computePwm(float temperatureC, float dtSeconds) {
  const float errorC = targetC - temperatureC;

  // A small overshoot immediately removes stored integral drive.
  if (errorC <= -OVERSHOOT_OFF_C) {
    integralTerm = 0.0f;
    return 0;
  }

  const float proportional = KP * errorC;
  float candidateIntegral = integralTerm + KI * errorC * dtSeconds;
  if (candidateIntegral < 0.0f) candidateIntegral = 0.0f;
  if (candidateIntegral > PWM_LIMIT) candidateIntegral = PWM_LIMIT;

  const float candidateOutput = proportional + candidateIntegral;
  // Anti-windup: integrate only when not pushing farther into upper saturation.
  if (candidateOutput < PWM_LIMIT || errorC < 0.0f) {
    integralTerm = candidateIntegral;
  }

  float requested = proportional + integralTerm;
  if (requested < 0.0f) requested = 0.0f;
  if (requested > PWM_LIMIT) requested = PWM_LIMIT;

  uint8_t requestedPwm = (uint8_t)(requested + 0.5f);
  if (requestedPwm > currentPwm + PWM_RISE_LIMIT_PER_STEP) {
    requestedPwm = currentPwm + PWM_RISE_LIMIT_PER_STEP;
  }
  return requestedPwm;
}

void controlStep(unsigned long nowMs) {
  float temperatureC = 0.0f;
  if (!readTemperatureC(temperatureC)) {
    if (sensorConversionPending && nowMs < 5000UL) {
      heaterOff();
      Serial.println(F("WAIT_SENSOR_FIRST_CONVERSION"));
      return;
    }
    latchFault(FAULT_SENSOR);
    return;
  }
  lastTemperatureC = temperatureC;

  if (temperatureC >= ABSOLUTE_CUTOFF_C) {
    latchFault(FAULT_OVERTEMP);
    return;
  }

  if (heaterArmed && nowMs - runStartedMs >= MAX_RUN_MS) {
    latchFault(FAULT_RUN_TIMEOUT);
    return;
  }

  float dtSeconds = (nowMs - lastControlMs) / 1000.0f;
  if (dtSeconds <= 0.0f || dtSeconds > 5.0f) {
    dtSeconds = 1.0f;
  }

  if (!heaterArmed || faultCode != FAULT_NONE) {
    heaterOff();
    integralTerm = 0.0f;
  } else {
    currentPwm = computePwm(temperatureC, dtSeconds);
    analogWrite(HEATER_PWM_PIN, currentPwm);
  }

  Serial.print(nowMs);
  Serial.print(',');
  Serial.print(targetC, 2);
  Serial.print(',');
  Serial.print(temperatureC, 3);
  Serial.print(',');
  Serial.print(currentPwm);
  Serial.print(',');
  Serial.print((currentPwm * 100.0f) / 255.0f, 1);
  Serial.print(',');
  if (faultCode != FAULT_NONE) {
    Serial.print(F("FAULT"));
  } else if (heaterArmed) {
    Serial.print(F("RUN"));
  } else {
    Serial.print(F("OFF"));
  }
  Serial.print(',');
  Serial.println(faultName(faultCode));
}

void setup() {
  // Establish the OFF level before starting Serial or I2C initialization.
  digitalWrite(HEATER_PWM_PIN, LOW);
  pinMode(HEATER_PWM_PIN, OUTPUT);
  heaterOff();

  Serial.begin(115200);
  const unsigned long serialWaitStart = millis();
  while (!Serial && millis() - serialWaitStart < 2000UL) {
  }

  Wire.begin();
  Wire.setClock(100000);
#if defined(WIRE_HAS_TIMEOUT)
  Wire.setWireTimeout(25000UL, true);
#endif

  tmp117Address = findTmp117();
  if (tmp117Address == 0) {
    latchFault(FAULT_SENSOR);
  }

  Serial.println();
  Serial.println(F("=== TMP117 + DFR0457 temperature controller ==="));
  Serial.println(F("Startup state: heater OFF"));
  Serial.print(F("PWM limit: "));
  Serial.print(PWM_LIMIT);
  Serial.print(F("/255, absolute cutoff: "));
  Serial.print(ABSOLUTE_CUTOFF_C, 1);
  Serial.println(F(" C"));
  printHelp();
  Serial.println(F("ms,target_c,temp_c,pwm,duty_pct,state,fault"));

  lastControlMs = millis();
}

void loop() {
  serviceSerial();

  const unsigned long nowMs = millis();
  if (nowMs - lastControlMs >= CONTROL_INTERVAL_MS) {
    controlStep(nowMs);
    lastControlMs = nowMs;
  }
}
