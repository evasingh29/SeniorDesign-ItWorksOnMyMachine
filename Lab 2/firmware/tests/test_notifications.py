"""Host tests of actual notification code with fake ESP32/SMTP APIs.

Run: python3 -m unittest discover -s 'Lab 2/firmware/tests' -v
Requires clang++ or g++; never reads secrets.h and never accesses the network.
Not an ESP32 build or hardware/FreeRTOS compatibility test.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

FIRMWARE = Path(__file__).resolve().parents[1] / 'receiver_esp32.ino'

STUBS = r'''
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <sys/time.h>
#include <string>
#include <deque>
#include <vector>
#include <stdexcept>
using std::max;
struct String {
  std::string data;
  String(const char* s):data(s) {}
  String(std::string s):data(s) {}
  String(uint32_t n):data(std::to_string(n)) {}
  const char* c_str() const { return data.c_str(); }
};
String operator+(const String& a, const String& b) { return a.data+b.data; }
std::string logs, lastBody, lastSubject;
struct SerialMock {
  void println(const char* s) { logs += std::string(s)+"\n"; }
  template<typename... Args> void printf(const char* f, Args... args) {
    char b[512]; snprintf(b,sizeof(b),f,args...); logs += b;
  }
} Serial;
uint64_t mockUs = 10000000;
int64_t esp_timer_get_time() { return mockUs; }
uint32_t millis() { return mockUs / 1000; }
using UBaseType_t = unsigned;
using portMUX_TYPE = int;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(x) ((void)(x))
#define portEXIT_CRITICAL(x) ((void)(x))
#define pdPASS 1
#define pdTRUE 1
#define portMAX_DELAY 0xffffffff
#define pdMS_TO_TICKS(x) (x)
void vTaskDelay(uint32_t ms) { mockUs += uint64_t(ms)*1000; }
struct FakeQueue { unsigned capacity, size; std::deque<std::vector<char>> events; };
using QueueHandle_t = FakeQueue*;
QueueHandle_t xQueueCreate(unsigned count, unsigned size) { return new FakeQueue{count,size,{}}; }
int xQueueSend(QueueHandle_t q, const void* event, unsigned wait) {
  assert(wait == 0);
  if (q->events.size() == q->capacity) return 0;
  const char* bytes = static_cast<const char*>(event);
  q->events.push_back(std::vector<char>(bytes,bytes+q->size)); return pdPASS;
}
struct QueueDrained {};
int xQueueReceive(QueueHandle_t q, void* event, unsigned) {
  if (q->events.empty()) throw QueueDrained{}; // terminates worker in host tests
  memcpy(event,q->events.front().data(),q->size); q->events.pop_front(); return pdTRUE;
}
#define WIFI_STA 1
#define WL_CONNECTED 1
struct WiFiMock {
  bool online = true;
  int status() { return online ? WL_CONNECTED : 0; }
  void reconnect() {}
  void mode(int) {}
  void begin(const char*,const char*) {}
} WiFi;
void sntp_set_time_sync_notification_cb(void (*)(timeval*)) {}
void configTzTime(const char* tz,const char*,const char*) { setenv("TZ",tz,1); tzset(); }
#define WIFI_SSID "placeholder"
#define WIFI_PASSWORD "placeholder"
#define SMTP_HOST "smtp.gmail.com"
#define SMTP_PORT 465
#define AUTHOR_EMAIL "sender@example.test"
#define AUTHOR_APP_PW "placeholder"
#define RECIPIENT "recipient@example.test"
#define GROUP_NAME "Group 6"
#define ALERT_SUBJECT "Beam Break"
struct Session_Config {
  struct { const char* host_name; int port; } server;
  struct { const char *email,*password,*user_domain; } login;
};
unsigned connects=0, sends=0, failsBeforeSuccess=0;
bool alwaysFail=false;
struct SMTPSession {
  bool connect(Session_Config*) { ++connects; return !alwaysFail && connects>failsBeforeSuccess; }
  void closeSession() {}
};
struct SMTP_Message {
  struct { const char *name,*email; } sender;
  const char* subject;
  struct { const char* content; } text;
  void addRecipient(const char*,const char*) {}
};
struct MailMock {
  void networkReconnect(bool) {}
  bool sendMail(SMTPSession*, SMTP_Message* message) {
    ++sends; lastBody=message->text.content; lastSubject=message->subject; return true;
  }
} MailClient;
struct BandMock { const char* name; float env; } bands[3] = {{"425-445",0},{"490-510",0},{"525-545",0}};
int activeBand=1;
bool calibratedOnce=true, beamBroken=true, armed=false;
float thrOff=2,thrOn=3;
uint32_t condSinceMs=0;
const uint32_t DEBOUNCE_MS=60;
const int LED_PIN=2, HIGH=1, LOW=0;
int led=HIGH;
void digitalWrite(int,int state) { led=state; }
void runDetection(uint32_t now);

'''

CHECKS = r'''
void drain() { try { alertTask(nullptr); } catch (QueueDrained&) {} }
void resetDelivery() { connects=sends=failsBeforeSuccess=0; alwaysFail=false; WiFi.online=true; logs.clear(); }
void syncAt(time_t epoch) { timeval tv={epoch,500000}; onTimeSync(&tv); }
int main() {
  setenv("TZ", "CST6CDT,M3.2.0,M11.1.0",1); tzset();
  alertQueue=xQueueCreate(ALERT_QUEUE_LENGTH,sizeof(AlertEvent));
  AlertEvent ev={}; ev.detectedUs=mockUs;
  assert(!resolveEventTime(ev)); // no fabricated timestamps before NTP
  timeval invalid={1,0}; onTimeSync(&invalid); assert(!resolveEventTime(ev));
  syncAt(1767283200); // Jan 1 2026, 16:00 UTC = 10 AM CST
  assert(resolveEventTime(ev)); time_t frozen=ev.timestamp;
  mockUs+=3000000; syncAt(1767283300); assert(resolveEventTime(ev)); assert(ev.timestamp==frozen);
  struct Case { time_t epoch; const char* expected; } cases[] = {
    {1767247500,"Critical Safety Event at 12:05 AM on 01/01/2026"},
    {1767290700,"Critical Safety Event at 12:05 PM on 01/01/2026"},
    {1782925500,"Critical Safety Event at 12:05 PM on 07/01/2026"}
  };
  for (const auto& c:cases) {
    resetDelivery(); ev.timestamp=c.epoch; ev.test=false; ev.band=1;
    assert(sendAlert(ev)); assert(lastBody.substr(0,lastBody.find('\n'))==c.expected);
  }
  // Actual unchanged detection logic: two breaks within one second, no held duplicates.
  breachCount=0; bands[1].env=4; runDetection(100); assert(!beamBroken && led==LOW);
  bands[1].env=0; runDetection(200); assert(beamBroken && led==HIGH);
  runDetection(300); runDetection(400); assert(breachCount==1);
  bands[1].env=4; runDetection(500); assert(!beamBroken);
  bands[1].env=0; runDetection(600); assert(breachCount==2);
  assert(alertQueue->events.size()==2);
  AlertEvent first,second; xQueueReceive(alertQueue,&first,0); xQueueReceive(alertQueue,&second,0);
  assert(first.number!=second.number && second.breachNumber==2);
  alertsEnabled=false; bands[1].env=4; runDetection(700);
  bands[1].env=0; runDetection(800); assert(alertQueue->events.empty());
  alertsEnabled=true;
  // FIFO order, immutable band/time snapshots, and explicit bounded overflow.
  resetDelivery(); nextEventNumber=breachCount=queueOverflowCount=0;
  for (unsigned i=0;i<ALERT_QUEUE_LENGTH;i++) { ++breachCount; queueAlert(false); mockUs+=1000000; }
  queueAlert(false); assert(queueOverflowCount==1);
  assert(logs.find("ALERT QUEUE OVERFLOW")!=std::string::npos);
  for (unsigned i=0;i<ALERT_QUEUE_LENGTH;i++) {
    AlertEvent item; xQueueReceive(alertQueue,&item,0);
    assert(item.number==i+1 && item.breachNumber==i+1 && !item.test && item.band==1);
    if (i) assert(item.detectedUs>10000000);
  }
  auto count=breachCount; queueAlert(true);
  AlertEvent test; xQueueReceive(alertQueue,&test,0); assert(test.test && breachCount==count);
  assert(sendAlert(test)); assert(lastSubject.find("TEST")!=std::string::npos);
  assert(lastBody.find("not a beam interruption")!=std::string::npos);
  // Retry succeeds, then still processes the next queued event.
  resetDelivery(); failsBeforeSuccess=2; queueAlert(false); queueAlert(false); drain();
  assert(connects==4 && sends==2 && alertQueue->events.empty());
  assert(logs.find("backoff_ms=2000")!=std::string::npos);
  assert(logs.find("backoff_ms=4000")!=std::string::npos);
  // Four attempts per event; exhausting one never clears the remaining queue.
  resetDelivery(); alwaysFail=true; queueAlert(false); queueAlert(false); drain();
  assert(connects==8 && sends==0 && alertQueue->events.empty());
  assert(logs.find("email failed FINAL")!=std::string::npos);
  assert(logs.find("backoff_ms=8000")!=std::string::npos);
  resetDelivery(); WiFi.online=false; queueAlert(false); drain();
  assert(connects==0 && sends==0 && logs.find("WiFi unavailable")!=std::string::npos);
  resetDelivery(); clockSynced=false; queueAlert(true); drain();
  assert(connects==0 && sends==0 && logs.find("NTP time invalid (not sent)")!=std::string::npos);
  // Backdate a pre-sync event rather than using the eventual delivery time.
  AlertEvent early={}; early.detectedUs=mockUs; mockUs+=10500000;
  syncAt(1767283200); assert(resolveEventTime(early)); assert(early.timestamp==1767283190);
  puts("Host notification checks passed (mock APIs; not an ESP32 build)");
}
'''


class NotificationHostTests(unittest.TestCase):
    def test_actual_notification_functions_with_mock_platform(self):
        compiler = shutil.which('clang++') or shutil.which('g++')
        if not compiler:
            self.skipTest('No host C++ compiler available')
        source = FIRMWARE.read_text()  # never read secrets.h
        events = source.split('// Only loop()/handleSerial()', 1)[1].split('// ---------------- spectrum', 1)[0]
        worker = source.split('bool ensureWiFi(', 1)[1].split('// ======================================================================\nvoid setup()', 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            cpp = Path(directory) / 'notifications.cpp'
            detection = source.split('// ---- detection: hysteresis + debounce ----')[1].split('  if (now - lastSerialMs')[0]
            cpp.write_text(STUBS + '\n// Only loop()/handleSerial()' + events +
                           '\nbool ensureWiFi(' + worker + '\nvoid runDetection(uint32_t now) {\n' + detection + '}\n' + CHECKS)
            binary = Path(directory) / 'notifications'
            built = subprocess.run([compiler, '-std=c++11', '-Wall', '-Wextra', '-Werror',
                                    str(cpp), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            ran = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stderr)
            self.assertIn('Host notification checks passed', ran.stdout)

    def test_queue_and_transition_static_contract(self):
        source = FIRMWARE.read_text()
        self.assertNotIn('ALERT_COOLDOWN_MS', source)
        self.assertNotIn('alertPending', source)
        self.assertIn('xQueueSend(alertQueue, &event, 0)', source)
        detection = source.split('// ---- detection: hysteresis + debounce ----')[1]
        self.assertIn('else if (now - condSinceMs >= DEBOUNCE_MS)', detection)
        self.assertEqual(detection.count('queueAlert(false)'), 1)
        self.assertIn('if (alertsEnabled) queueAlert(false)', detection)
        self.assertIn('digitalWrite(LED_PIN, beamBroken ? HIGH : LOW)', detection)


if __name__ == '__main__':
    unittest.main()
