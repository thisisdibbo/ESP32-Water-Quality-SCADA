#include <Wire.h>
#include <SPI.h>
#include <SD.h>
#include <RTClib.h>
#include <TinyGPSPlus.h>
#include <HardwareSerial.h>

#include <OneWire.h>
#include <DallasTemperature.h>

// ================= PINS =================
#define TDS_PIN 33
#define SD_CS   5

#define GPS_RX 4
#define GPS_TX 2

#define TEMP_PIN 16   // DS18B20 (10k pull-up used externally)

// ================= GPS =================
HardwareSerial gpsSerial(1);
TinyGPSPlus gps;

// ================= RTC =================
RTC_DS3231 rtc;
File logFile;

// ================= TEMP SENSOR =================
OneWire oneWire(TEMP_PIN);
DallasTemperature sensors(&oneWire);

// ================= SETUP =================
void setup() {

  Serial.begin(115200);

  analogReadResolution(12);
  pinMode(TDS_PIN, INPUT);

  pinMode(TEMP_PIN, INPUT_PULLUP);

  Wire.begin(21, 22);

  if (!rtc.begin()) {
    Serial.println("❌ RTC not found");
  } else {
    Serial.println("✅ RTC Ready");
  }

  gpsSerial.begin(9600, SERIAL_8N1, GPS_RX, GPS_TX);
  Serial.println("✅ GPS Started");

  SPI.begin(18, 19, 23, SD_CS);

  if (!SD.begin(SD_CS)) {
    Serial.println("❌ SD Failed");
  } else {
    Serial.println("✅ SD Ready");

    logFile = SD.open("/water_log.csv", FILE_APPEND);

    if (logFile && logFile.size() == 0) {
      logFile.println("Time,ADC,Voltage,EC,TDS,Temp,Lat,Lon,Speed,Sats");
      logFile.close();
    }
  }

  sensors.begin();
  Serial.println("✅ DS18B20 Ready");

  Serial.println("SYSTEM READY");
}

// ================= TIME FUNCTION =================
String getTime() {

  DateTime now = rtc.now();

  char buf[25];

  sprintf(buf,
          "%04d-%02d-%02d %02d:%02d:%02d",
          now.year(),
          now.month(),
          now.day(),
          now.hour(),
          now.minute(),
          now.second());

  return String(buf);
}

// ================= STABLE TEMP READ =================
float readTemperature() {

  float sum = 0;
  int valid = 0;

  for (int i = 0; i < 5; i++) {

    sensors.requestTemperatures();
    delay(750);

    float t = sensors.getTempCByIndex(0);

    if (t != DEVICE_DISCONNECTED_C && t > -55 && t < 125) {
      sum += t;
      valid++;
    }

    delay(100);
  }

  if (valid == 0) return DEVICE_DISCONNECTED_C;

  return sum / valid;
}

// ================= LOOP =================
void loop() {

  while (gpsSerial.available()) {
    gps.encode(gpsSerial.read());
  }

  float tempC = readTemperature();

  long sum = 0;

  for (int i = 0; i < 20; i++) {
    sum += analogRead(TDS_PIN);
    delay(5);
  }

  float adc = sum / 20.0;
  float voltage = adc * (3.3 / 4095.0);

  float ec = (133.42 * voltage * voltage * voltage
            - 255.86 * voltage * voltage
            + 857.39 * voltage);

  ec = ec / 1000.0;

  if (ec < 0) ec = 0;

  float tds = ec * 500.0;

  float lat = gps.location.isValid() ? gps.location.lat() : 0.0;
  float lon = gps.location.isValid() ? gps.location.lng() : 0.0;
  float speed = gps.speed.isValid() ? gps.speed.kmph() : 0.0;
  int sats = gps.satellites.isValid() ? gps.satellites.value() : 0;

  String timestamp = getTime();

  // ================= SERIAL OUTPUT (HUMAN READABLE) =================
  Serial.println("---------------------");

  Serial.print("Time: ");
  Serial.println(timestamp);

  Serial.print("TDS: ");
  Serial.print(tds);
  Serial.println(" ppm");

  Serial.print("EC: ");
  Serial.print(ec, 3);
  Serial.println(" mS/cm");

  Serial.print("Temp: ");
  if (tempC == DEVICE_DISCONNECTED_C) {
    Serial.println("❌ Not detected");
  } else {
    Serial.print(tempC);
    Serial.println(" °C");
  }

  Serial.print("GPS: ");
  Serial.print(lat, 6);
  Serial.print(", ");
  Serial.print(lon, 6);
  Serial.print(" | Speed: ");
  Serial.print(speed);
  Serial.print(" km/h | Sats: ");
  Serial.println(sats);

  // ================= SD LOG =================
  logFile = SD.open("/water_log.csv", FILE_APPEND);

  if (logFile) {

    logFile.print(timestamp); logFile.print(",");
    logFile.print(adc); logFile.print(",");
    logFile.print(voltage, 3); logFile.print(",");
    logFile.print(ec, 3); logFile.print(",");
    logFile.print(tds, 1); logFile.print(",");
    logFile.print(tempC); logFile.print(",");
    logFile.print(lat, 6); logFile.print(",");
    logFile.print(lon, 6); logFile.print(",");
    logFile.print(speed); logFile.print(","); logFile.println(sats);

    logFile.close();
  }

  // =========================================================
  // 🚀 PYTHON SCADA OUTPUT (EXTRA LINE - ADDED ONLY)
  // FORMAT:
  // tds,ec,temp,ph,time,lat,lon,speed,sats
  // =========================================================

  float ph = 0.0;

  if (tempC == DEVICE_DISCONNECTED_C) {
    tempC = 0.0;
  }

  Serial.print(tds);
  Serial.print(",");
  Serial.print(ec);
  Serial.print(",");
  Serial.print(tempC);
  Serial.print(",");
  Serial.print(ph);
  Serial.print(",");
  Serial.print(timestamp);
  Serial.print(",");
  Serial.print(lat, 6);
  Serial.print(",");
  Serial.print(lon, 6);
  Serial.print(",");
  Serial.print(speed);
  Serial.print(",");
  Serial.println(sats);

  delay(1000);
}