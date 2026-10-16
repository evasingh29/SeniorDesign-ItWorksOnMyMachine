"""USB protocol tests using actual receiver code and mocked Arduino APIs.

No hardware, network, secrets, or ESP32 libraries are used. The full sketch is
syntax-checked on the host; actual ESP32 compilation still requires its board core.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

FIRMWARE = Path(__file__).resolve().parents[1] / 'receiver_esp32.ino'

ARDUINO = r'''
#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <string>
using std::max;
#define PI 3.14159265358979323846
#define OUTPUT 1
#define HIGH 1
#define LOW 0
#define ADC_11db 3
extern std::string serialOutput;
extern int ledState;
struct SerialMock {
  void setTxBufferSize(unsigned) {}
  void begin(unsigned baud) { if (baud != 115200) std::abort(); }
  bool available() { return false; }
  char read() { return 0; }
  void println(const char* text) { serialOutput += std::string(text)+"\n"; }
  template<typename... Args> void printf(const char* format, Args... args) {
    char text[1024]; snprintf(text,sizeof(text),format,args...); serialOutput += text;
  }
};
extern SerialMock Serial;
inline uint32_t millis() { return 0; }
inline uint32_t micros() { return 0; }
inline void delay(unsigned) {}
inline void pinMode(int,int) {}
inline void digitalWrite(int,int state) { ledState=state; }
inline void analogReadResolution(int) {}
inline void analogSetPinAttenuation(int,int) {}
inline int analogRead(int) { return 2048; }
'''
TASKS = r'''
#pragma once
#include <cstdint>
using TaskHandle_t = void*;
#define pdTRUE 1
#define portMAX_DELAY 0xffffffff
inline unsigned ulTaskNotifyTake(int,unsigned) { return 0; }
inline void xTaskNotifyGive(TaskHandle_t) {}
inline int xTaskCreatePinnedToCore(void (*)(void*), const char*, unsigned,
                                void*, int, TaskHandle_t*, int) { return 1; }
'''


class SerialProtocolTests(unittest.TestCase):
    def test_no_embedded_network_or_credentials(self):
        source = FIRMWARE.read_text()
        for dependency in ['WiFi.h', 'ESP_Mail_Client.h', 'secrets.h', 'configTzTime',
                           'sendAlert(', 'alertPending', 'ALERT_COOLDOWN_MS']:
            self.assertNotIn(dependency, source)
        self.assertIn('Serial.begin(115200)', source)

    def test_full_sketch_syntax_and_actual_debounced_events(self):
        compiler = shutil.which('clang++') or shutil.which('g++')
        if not compiler:
            self.skipTest('No host C++ compiler available')
        source = FIRMWARE.read_text()
        detection = source.split('// ---- detection: hysteresis + debounce ----')[1].split(
            '  if (now - lastSerialMs')[0]
        checks = r'''
#include <cassert>
std::string serialOutput;
int ledState=HIGH;
SerialMock Serial;
void detect(uint32_t now) {
DETECTION
}
unsigned occurrences(const std::string& token) {
  unsigned count=0; size_t at=0;
  while ((at=serialOutput.find(token,at))!=std::string::npos) { ++count; at+=token.size(); }
  return count;
}
int main() {
  setup(); // exercise 115200 setup, original band configuration and calibration start
  assert(ADC_PIN==34 && LED_PIN==2 && SAMPLE_RATE==4000 && TS_US==250);
  serialOutput.clear();
  calibratedOnce=true; condSinceMs=0;
  bands[activeBand].env=0; detect(100); // boot blocked never emits a breach
  assert(occurrences("BREACH\n")==0);
  bands[activeBand].env=10; detect(200); // restore/arm
  assert(!beamBroken && ledState==LOW && occurrences("CLEAR\n")==1);
  detect(210); // keep present and start the debounce reference
  bands[activeBand].env=0; detect(230); // less than 60ms -> no event
  assert(!beamBroken && occurrences("BREACH\n")==0);
  detect(280); assert(beamBroken && ledState==HIGH);
  detect(400); detect(16000); // continuously blocked -> no duplicates
  assert(occurrences("BREACH\n")==1);
  bands[activeBand].env=10; detect(16100); assert(!beamBroken && ledState==LOW);
  bands[activeBand].env=0; detect(16200); assert(beamBroken && ledState==HIGH);
  bands[activeBand].env=10; detect(16300);
  bands[activeBand].env=0; detect(16400); // distinct break 200ms later
  assert(occurrences("BREACH\n")==3 && occurrences("CLEAR\n")==3);
  // Emit real firmware output for the companion Python parser integration test.
  printf("%s",serialOutput.c_str());
}
'''.replace('DETECTION', detection)
        with tempfile.TemporaryDirectory(prefix='lab2-usb-protocol-') as directory:
            root = Path(directory)
            (root/'Arduino.h').write_text(ARDUINO)
            (root/'freertos').mkdir()
            (root/'freertos/FreeRTOS.h').write_text(TASKS)
            (root/'freertos/task.h').write_text('#pragma once\n#include "FreeRTOS.h"\n')
            cpp = root/'receiver.cpp'
            cpp.write_text(source+checks)
            binary = root/'receiver'
            built = subprocess.run([compiler,'-std=c++11','-Wall','-Wextra','-Werror',
                                    '-I',str(root),str(cpp),'-o',str(binary)],
                                   capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran = subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stderr)
            # Load existing Python processor without changing import paths permanently.
            import sys
            from unittest.mock import Mock, patch
            with patch.object(sys,'path',[str(FIRMWARE.parents[1]/'alert')]+sys.path):
                from main import EventProcessor
                sender = Mock()
                processor = EventProcessor(sender)
                for line in ran.stdout.splitlines():
                    processor.process(line)
                self.assertEqual(sender.submit.call_count,3)
                self.assertTrue(processor.active)


if __name__ == '__main__':
    unittest.main()
