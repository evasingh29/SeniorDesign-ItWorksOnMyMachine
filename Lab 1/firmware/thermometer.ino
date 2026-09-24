#include <LiquidCrystal.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// ================= NETWORK ON/OFF SWITCH =================
#define ENABLE_NETWORK 1

#if ENABLE_NETWORK
  #include <WiFi.h>
  #include <WiFiClientSecure.h>
  #include <PubSubClient.h>
  #include <ArduinoJson.h>

  // ================= WIFI =================
  #define WIFI_SSID "iPhone"
  #define WIFI_PASSWORD "illgiveMyselfalltheflowers"

  // ================= HIVEMQ CLOUD =================
  #define MQTT_BROKER "899493da75014d42be31bcfe3c7c3815.s1.eu.hivemq.cloud"
  #define MQTT_PORT 8883
  #define MQTT_USER "thermometer"
  #define MQTT_PASS "ItWorksOnMyMachine"
  #define MQTT_CLIENT_ID "esp32-thermometer-box"
#endif

// ================= PIN DEFINITIONS =================

#define ONE_WIRE_BUS 4
#define BUTTON1 18
#define BUTTON2 19

LiquidCrystal lcd(21, 22, 23, 25, 26, 27);
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

// ================= SENSOR ADDRESSES =================

DeviceAddress sensor1 = {
  0x28, 0x31, 0xF5, 0xA8,
  0x11, 0x00, 0x00, 0xE4
};

DeviceAddress sensor2 = {
  0x28, 0xF4, 0xC4, 0xEB,
  0x10, 0x00, 0x00, 0x1A
};

// ================= SHARED STATE =================
volatile float temp1 = -127;
volatile float temp2 = -127;

volatile bool sensor1DisplayOn = false;
volatile bool sensor2DisplayOn = false;

// Set whenever a display state changes; the network task publishes it.
volatile bool statesDirty = true;

// ================= BUTTONS (debounced) =================

struct Btn {
  uint8_t pin;
  int stable;
  int raw;
  unsigned long changed;
};

Btn btn1 = {BUTTON1, HIGH, HIGH, 0};
Btn btn2 = {BUTTON2, HIGH, HIGH, 0};
const unsigned long DEBOUNCE_MS = 30;

// ================= TIMING =================

unsigned long conversionStart = 0;
bool conversionRunning = false;
const unsigned long CONVERSION_TIME = 750;

unsigned long lastDisplay = 0;
const unsigned long DISPLAY_TIME = 200; //only redraws changed lines

// ================= NETWORK STATE =================

#if ENABLE_NETWORK
const char* TOPIC_S1_TEMP   = "thermometer/sensor/1/temperature";
const char* TOPIC_S2_TEMP   = "thermometer/sensor/2/temperature";
const char* TOPIC_S1_STATUS = "thermometer/sensor/1/status";
const char* TOPIC_S2_STATUS = "thermometer/sensor/2/status";
const char* TOPIC_B1_STATE  = "thermometer/button/1/state";
const char* TOPIC_B2_STATE  = "thermometer/button/2/state";
const char* TOPIC_CMD_B1    = "thermometer/command/button/1";
const char* TOPIC_CMD_B2    = "thermometer/command/button/2";

WiFiClientSecure secureClient;
PubSubClient mqtt(secureClient);

const unsigned long PUBLISH_INTERVAL_MS = 1000;
unsigned long lastPublishMs = 0;

unsigned long wifiAttemptStartedMs = 0;
unsigned long wifiNextAttemptMs = 0;
bool wifiAttemptInProgress = false;

const unsigned long WIFI_CONNECT_TIMEOUT_MS = 10000;
const unsigned long WIFI_RETRY_MS = 15000;

unsigned long lastMqttAttemptMs = 0;
const unsigned long MQTT_RETRY_MS = 3000;

// forward declarations
void networkTask(void*);
void handleWiFi();
void connectWiFi();
void connectMqtt();
void onMqttMessage(char* topic, byte* payload, unsigned int length);
void publishReadings();
void publishOne(const char* tempTopic, const char* statusTopic, float tempC);
void publishButtonStates();
#endif

// forward declarations
bool working(float temp);
void updateDisplay();
void startConversion();
void checkTemperature();
void checkButtons();
bool pressed(Btn &b);

// ================= SETUP =================

void setup() {

  Serial.begin(115200);

  pinMode(BUTTON1, INPUT_PULLUP);
  pinMode(BUTTON2, INPUT_PULLUP);

  btn1.stable = btn1.raw = digitalRead(BUTTON1);
  btn2.stable = btn2.raw = digitalRead(BUTTON2);

  lcd.begin(16, 2);
  lcd.clear(); // only clear once, at startup

  sensors.begin();
  sensors.setResolution(sensor1, 12);
  sensors.setResolution(sensor2, 12);
  sensors.setWaitForConversion(false);

  updateDisplay();
  startConversion();

#if ENABLE_NETWORK
  // never freezes the sensors, buttons, or LCD on core 1.
  xTaskCreatePinnedToCore(networkTask, "net", 12288, NULL, 1, NULL, 0);
#else
  Serial.println("ENABLE_NETWORK is 0 - running sensors/LCD/buttons standalone.");
#endif
}

// ================= MAIN LOOP (core 1) =================

void loop() {

  checkButtons();
  checkTemperature();

  if (millis() - lastDisplay >= DISPLAY_TIME) {
    lastDisplay = millis();
    updateDisplay();
  }

  delay(5);
}

// ================= BUTTONS =================

bool pressed(Btn &b) {
  int r = digitalRead(b.pin);

  if (r != b.raw) {
    b.raw = r;
    b.changed = millis();
  }

  if (millis() - b.changed >= DEBOUNCE_MS && r != b.stable) {
    b.stable = r;
    return r == LOW;
  }

  return false;
}

void checkButtons() {
  // Each button toggles only that sensor's LCD display state.
  if (pressed(btn1)) {
    sensor1DisplayOn = !sensor1DisplayOn;
    statesDirty = true;
    updateDisplay();
  }

  if (pressed(btn2)) {
    sensor2DisplayOn = !sensor2DisplayOn;
    statesDirty = true;
    updateDisplay();
  }
}

// ================= TEMPERATURE =================

void startConversion() {
  sensors.requestTemperatures();
  conversionStart = millis();
  conversionRunning = true;
}

void checkTemperature() {

  if (!conversionRunning)
    return;

  if (millis() - conversionStart < CONVERSION_TIME)
    return;

  temp1 = sensors.getTempC(sensor1);
  temp2 = sensors.getTempC(sensor2);

  conversionRunning = false;
  startConversion();
}

bool working(float temp) {
  // -127 = disconnected; 85.0 = power-on reset value after a replug
  return temp != DEVICE_DISCONNECTED_C && temp != -127.0 && temp != 85.0;
}

// ================= DISPLAY =================
// when its text actually changes, so there's no flicker.
void printLine(int row, const char* text) {
  char buf[17];
  snprintf(buf, sizeof(buf), "%-16s", text);
  lcd.setCursor(0, row);
  lcd.print(buf);
}

void formatSensor(char* out, size_t n, int num, bool on, float t) {
  if (!on)              snprintf(out, n, "S%d OFF", num);
  else if (!working(t)) snprintf(out, n, "S%d ERROR", num);
  else                  snprintf(out, n, "S%d %.1f C", num, t);
}

void updateDisplay() {
  static char last0[17] = "";
  static char last1[17] = "";
  char l0[17], l1[17];

  formatSensor(l0, sizeof(l0), 1, sensor1DisplayOn, temp1);
  formatSensor(l1, sizeof(l1), 2, sensor2DisplayOn, temp2);

  if (strcmp(l0, last0) != 0) { printLine(0, l0); strcpy(last0, l0); }
  if (strcmp(l1, last1) != 0) { printLine(1, l1); strcpy(last1, l1); }
}

#if ENABLE_NETWORK
// ================= NETWORK TASK (core 0) =================

void networkTask(void*) {

  secureClient.setInsecure(); // fine for a class lab; use setCACert() for production
  mqtt.setServer(MQTT_BROKER, MQTT_PORT);
  mqtt.setCallback(onMqttMessage);
  mqtt.setSocketTimeout(5);

  for (;;) {
    handleWiFi();

    if (WiFi.status() == WL_CONNECTED) {
      unsigned long now = millis();

      if (!mqtt.connected() && now - lastMqttAttemptMs >= MQTT_RETRY_MS) {
        lastMqttAttemptMs = now;
        connectMqtt();
      }

      mqtt.loop();

      if (mqtt.connected()) {
        if (statesDirty) {
          statesDirty = false;
          publishButtonStates();
        }

        if (now - lastPublishMs >= PUBLISH_INTERVAL_MS) {
          lastPublishMs = now;
          publishReadings();
          publishButtonStates();
        }
      }
    }

    vTaskDelay(pdMS_TO_TICKS(10));
  }
}

// ================= WIFI =================

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  Serial.println("WiFi: starting connection attempt...");
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  wifiAttemptStartedMs = millis();
  wifiAttemptInProgress = true;
}

void handleWiFi() {

  unsigned long now = millis();

  if (WiFi.status() == WL_CONNECTED) {
    if (wifiAttemptInProgress) {
      Serial.print("WiFi: connected! IP: ");
      Serial.println(WiFi.localIP());
    }
    wifiAttemptInProgress = false;
    return;
  }

  if (wifiAttemptInProgress) {
    if (now - wifiAttemptStartedMs >= WIFI_CONNECT_TIMEOUT_MS) {
      Serial.println("WiFi: network unavailable. Continuing in offline mode.");
      WiFi.disconnect();
      wifiAttemptInProgress = false;
      wifiNextAttemptMs = now + WIFI_RETRY_MS;
    }
    return;
  }

  if ((long)(now - wifiNextAttemptMs) < 0) {
    return;
  }

  connectWiFi();
}

// ================= MQTT =================

void connectMqtt() {
  if (WiFi.status() != WL_CONNECTED) return;

  Serial.println("MQTT: attempting connection...");
  if (mqtt.connect(MQTT_CLIENT_ID, MQTT_USER, MQTT_PASS)) {
    mqtt.subscribe(TOPIC_CMD_B1);
    mqtt.subscribe(TOPIC_CMD_B2);
    Serial.println("MQTT: connected.");
    publishButtonStates();
  } else {
    Serial.print("MQTT: failed, state=");
    Serial.println(mqtt.state());
  }
}

// Only updates state; the main loop redraws the LCD within 200 ms.
void onMqttMessage(char* topic, byte* payload, unsigned int length) {
  StaticJsonDocument<128> doc;
  if (deserializeJson(doc, payload, length)) return;

  bool on = doc["on"] | false;

  if (strcmp(topic, TOPIC_CMD_B1) == 0) {
    sensor1DisplayOn = on;
  } else if (strcmp(topic, TOPIC_CMD_B2) == 0) {
    sensor2DisplayOn = on;
  }

  statesDirty = true;
}

// ================= CLOUD PUBLISH =================

void publishReadings() {
  publishOne(TOPIC_S1_TEMP, TOPIC_S1_STATUS, temp1);
  publishOne(TOPIC_S2_TEMP, TOPIC_S2_STATUS, temp2);
}

void publishOne(const char* tempTopic, const char* statusTopic, float tempC) {
  StaticJsonDocument<128> doc;
  bool ok = working(tempC);
  doc["ok"] = ok;
  if (ok) {
    doc["c"] = round(tempC * 10) / 10.0;
  } else {
    doc["err"] = "unplugged";
  }
  char buf[128];
  serializeJson(doc, buf);
  mqtt.publish(tempTopic, buf);
  mqtt.publish(statusTopic, buf);
}

void publishButtonStates() {
  StaticJsonDocument<64> doc1;
  doc1["on"] = (bool)sensor1DisplayOn;
  char buf1[64];
  serializeJson(doc1, buf1);
  mqtt.publish(TOPIC_B1_STATE, buf1, true);

  StaticJsonDocument<64> doc2;
  doc2["on"] = (bool)sensor2DisplayOn;
  char buf2[64];
  serializeJson(doc2, buf2);
  mqtt.publish(TOPIC_B2_STATE, buf2, true);
}
#endif // ENABLE_NETWORK
