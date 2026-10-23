/*
  ECE:4880 Lab 2 — Electric Eye receiver, FINAL (ESP32)
 
  Meets the checkoff criteria:
    - LED (GPIO2) ON when the beam is broken, OFF when the transmitter beam is received
    - Ignores lamp IR noise: 3 digital band-pass filters, one per candidate range
        band 1 = 425-445 Hz, band 2 = 490-510 Hz, band 3 = 525-545 Hz
    - USB serial BREACH/CLEAR events; Python on the Mac sends Gmail notifications
    - Experiment data: CSV every 200 ms with all 3 band levels + measured peak frequency,
      and a full spectrum dump on request
 
  Dependencies: ESP32 Arduino core only; no Wi-Fi/mail library or secrets header
  Board:   ESP32 Dev Module
 
  STARTUP: power up with the beam BLOCKED (lamp on if testing with lamp).
           It auto-calibrates the noise floor for ~2.5 s, then unblock the beam.
 
  Serial Monitor (115200) — send one character:
    1 / 2 / 3 : select detection band (425-445 / 490-510 / 525-545)
    b         : recalibrate NOISE  (beam BLOCKED, lamp ON)   2 s
    p         : calibrate SIGNAL   (beam CLEAR,   lamp ON)   2 s  (optional, refines thresholds)
    r         : reset thresholds
    q         : toggle CSV logging
    s         : dump one full spectrum (freq_hz, amp_mV, amp_dB)
    e / t     : print help for Python email controls (no synthetic beam events)
*/
 
#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

// ===================== RECEIVER CONFIG =====================
const int DEFAULT_BAND = 2;      // 1, 2 or 3 — set to the band your experiment identifies
 
const int ADC_PIN = 34;          // ADC1 pin (ADC2 pins don't work with WiFi on)
const int LED_PIN = 2;           // onboard LED: ON = beam broken
 
const float    SAMPLE_RATE    = 4000.0f;
const uint32_t TS_US = 250;
 
const float ON_FACTOR   = 3.0f;  // beam PRESENT when level > noise * ON_FACTOR
const float OFF_FACTOR  = 2.0f;  // beam BROKEN  when level < noise * OFF_FACTOR
const float MIN_THR     = 1.0f;
const float ENV_TAU_S   = 0.030f;
const uint32_t DEBOUNCE_MS       = 60;
const float BW_SCALE    = 1.5f;
 
const float ADC_FULL_SCALE_V = 3.1f;
const float DIVIDER_GAIN     = 2.0f;   // 10k/10k divider before the ADC
 
const int   N_BLOCK = 800;             // 200 ms blocks, 5 Hz bins
const float HP_CUTOFF = 160.0f;      // ignore everything below this (lamp flicker, 60/120 Hz)
const float SCAN_LO = HP_CUTOFF, SCAN_HI = 1000.0f;
const float TX_LO   = 400.0f, TX_HI   = 600.0f;
// =======================================================
 
// ---------------- band-pass biquad (RBJ, 0 dB peak) ----------------
struct Biquad {
  float b0 = 0, b2 = 0, a1 = 0, a2 = 0, z1 = 0, z2 = 0;
  void set(float f0, float bw) {
    float w0 = 2.0f * PI * f0 / SAMPLE_RATE;
    float alpha = sinf(w0) / (2.0f * (f0 / bw));
    float a0 = 1.0f + alpha;
    b0 = alpha / a0; b2 = -alpha / a0;
    a1 = -2.0f * cosf(w0) / a0; a2 = (1.0f - alpha) / a0;
    z1 = z2 = 0;
  }
  inline float process(float x) {
    float y = b0 * x + z1;
    z1 = -a1 * y + z2;
    z2 = b2 * x - a2 * y;
    return y;
  }
};
 
// ---------------- high-pass biquad (RBJ, Butterworth sections) ----------------
struct HighPass {
  float b0 = 0, b1 = 0, b2 = 0, a1 = 0, a2 = 0, z1 = 0, z2 = 0;
  void set(float fc, float q) {
    float w0 = 2.0f * PI * fc / SAMPLE_RATE;
    float alpha = sinf(w0) / (2.0f * q), cw = cosf(w0);
    float a0 = 1.0f + alpha;
    b0 = (1.0f + cw) / 2.0f / a0; b1 = -(1.0f + cw) / a0; b2 = b0;
    a1 = -2.0f * cw / a0; a2 = (1.0f - alpha) / a0;
    z1 = z2 = 0;
  }
  inline float process(float x) {
    float y = b0 * x + z1;
    z1 = b1 * x - a1 * y + z2;
    z2 = b2 * x - a2 * y;
    return y;
  }
};
HighPass hp1, hp2;               // 4th-order Butterworth high-pass at HP_CUTOFF

struct Band {
  const char* name = "";
  Biquad s1, s2;
  float env = 0;
  void init(const char* n, float lo, float hi) {
    name = n;
    float f0 = 0.5f * (lo + hi), bw = (hi - lo) * BW_SCALE;
    s1.set(f0, bw); s2.set(f0, bw); env = 0;
  }
  inline void update(float x, float k) {
    env += k * (fabsf(s2.process(s1.process(x))) - env);
  }
};
 
Band bands[3];
int activeBand = DEFAULT_BAND - 1;
 
// ---------------- detection / calibration ----------------
float thrOn = 3.0f, thrOff = 2.0f;
float noiseCal[3] = {-1, -1, -1}, sigCal[3] = {-1, -1, -1};
bool calibratedOnce = false;
bool beamBroken = true;          // assume blocked at boot
uint32_t condSinceMs = 0;
 
enum CalMode { CAL_NONE, CAL_NOISE, CAL_SIGNAL };
void startCal(CalMode m, uint32_t delayMs);
CalMode calMode = CAL_NONE;
uint32_t calStartMs = 0;
double calAccum[3] = {0, 0, 0};
uint32_t calCount = 0;
 
// ---------------- spectrum ----------------
float bufA[N_BLOCK], bufB[N_BLOCK];
float* fillBuf = bufA;
float* volatile readyBuf = nullptr;
int fillIdx = 0;
float hannW[N_BLOCK];
const int MAX_BINS = 200;
float binFreq[MAX_BINS], binCoeff[MAX_BINS], binAmp[MAX_BINS];
int nBins = 0;
TaskHandle_t analysisHandle = nullptr;
 
volatile bool logCsv = true;
volatile bool spectrumRequest = false;
volatile uint32_t missed = 0;
 
float dcEst = 0, envK = 0;
 
// ======================================================================
void recomputeThresholds() {
  int i = activeBand;
  if (noiseCal[i] >= 0 && sigCal[i] > noiseCal[i] * 1.5f) {
    float span = sigCal[i] - noiseCal[i];
    thrOff = noiseCal[i] + 0.35f * span;
    thrOn  = noiseCal[i] + 0.60f * span;
  } else if (noiseCal[i] >= 0) {
    thrOff = max(noiseCal[i] * OFF_FACTOR, MIN_THR * 0.6f);
    thrOn  = max(noiseCal[i] * ON_FACTOR,  MIN_THR);
  }
  Serial.printf("# band %d (%s Hz)  thrOff=%.2f  thrOn=%.2f\n", i + 1, bands[i].name, thrOff, thrOn);
}
 
void startCal(CalMode m, uint32_t delayMs) {
  calMode = m;
  calStartMs = millis() + delayMs;
  calAccum[0] = calAccum[1] = calAccum[2] = 0;
  calCount = 0;
  Serial.printf("# calibrating %s...\n", m == CAL_NOISE ? "NOISE - keep beam BLOCKED" : "SIGNAL - keep beam CLEAR");
}
 
void handleSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    switch (c) {
      case '1': case '2': case '3':
        activeBand = c - '1';
        recomputeThresholds();
        break;
      case 'b': startCal(CAL_NOISE, 0); break;
      case 'p': startCal(CAL_SIGNAL, 0); break;
      case 'r':
        for (int i = 0; i < 3; i++) noiseCal[i] = sigCal[i] = -1;
        thrOn = 3.0f; thrOff = 2.0f;
        Serial.println("# thresholds reset - send 'b' with beam blocked");
        break;
      case 'q': logCsv = !logCsv; break;
      case 's': spectrumRequest = true; break;
      case 'e':
        Serial.println("# Email runs on the Mac; start/stop Python to enable/disable delivery");
        break;
      case 't':
        Serial.println("# Test email on Mac: python main.py --test-email (no beam event emitted)");
        break;
    }
  }
}
 
float countsToMv(float c) { return c * ADC_FULL_SCALE_V / 4095.0f * 1000.0f; }
 
float findPeak(int iLo, int iHi, float* ampOut) {
  int best = iLo;
  for (int i = iLo; i <= iHi; i++) if (binAmp[i] > binAmp[best]) best = i;
  *ampOut = binAmp[best];
  float f = binFreq[best];
  if (best > 0 && best < nBins - 1 && binAmp[best - 1] > 0 && binAmp[best + 1] > 0 && binAmp[best] > 0) {
    float a = logf(binAmp[best - 1]), b = logf(binAmp[best]), c = logf(binAmp[best + 1]);
    float den = a - 2.0f * b + c;
    if (den != 0) {
      float d = 0.5f * (a - c) / den;
      if (d > -1 && d < 1) f += d * (binFreq[1] - binFreq[0]);
    }
  }
  return f;
}
 
// ---------------- spectrum + CSV (core 0) ----------------
void analysisTask(void*) {
  for (;;) {
    ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    float* x = readyBuf;
    if (!x) continue;
 
    double sum = 0; float mn = 1e9, mx = -1e9;
    for (int n = 0; n < N_BLOCK; n++) { sum += x[n]; if (x[n] < mn) mn = x[n]; if (x[n] > mx) mx = x[n]; }
    float mean = sum / N_BLOCK;
    double ss = 0;
    for (int n = 0; n < N_BLOCK; n++) { float d = x[n] - mean; ss += d * d; }
    float rmsCounts = sqrtf(ss / N_BLOCK);
 
    const float wSum = N_BLOCK * 0.5f;
    for (int k = 0; k < nBins; k++) {
      float c = binCoeff[k], s1 = 0, s2 = 0;
      for (int n = 0; n < N_BLOCK; n++) {
        float s0 = (x[n] - mean) * hannW[n] + c * s1 - s2;
        s2 = s1; s1 = s0;
      }
      float p = s1 * s1 + s2 * s2 - c * s1 * s2;
      binAmp[k] = 2.0f * sqrtf(p > 0 ? p : 0) / wSum;
    }
 
    int iTxLo = 0, iTxHi = nBins - 1;
    for (int k = 0; k < nBins; k++) { if (binFreq[k] < TX_LO) iTxLo = k + 1; if (binFreq[k] <= TX_HI) iTxHi = k; }
    float aTx, aAll;
    float fTx  = findPeak(iTxLo, iTxHi, &aTx);
    float fAll = findPeak(0, nBins - 1, &aAll);
 
    if (logCsv) {
      Serial.printf("%lu,%.1f,%.2f,%.1f,%.2f,%.2f,%.1f,%.2f,%.2f,%.2f,%d,%d,%d,%d,%lu\n",
        (unsigned long)millis(),
        fTx, countsToMv(aTx), fAll, countsToMv(aAll),
        countsToMv(rmsCounts), countsToMv(rmsCounts) * DIVIDER_GAIN,
        bands[0].env, bands[1].env, bands[2].env,
        activeBand + 1, beamBroken ? 1 : 0, (int)mn, (int)mx, (unsigned long)missed);
      if (mn < 30 || mx > 4065) Serial.println("# WARNING: ADC clipping - reduce analog gain");
    }
 
    if (spectrumRequest) {
      spectrumRequest = false;
      Serial.println("# SPECTRUM_BEGIN freq_hz,amp_mV_at_adc,amp_dB_re_1mV");
      for (int k = 0; k < nBins; k++) {
        float mv = countsToMv(binAmp[k]);
        Serial.printf("%.1f,%.3f,%.2f\n", binFreq[k], mv, 20.0f * log10f(mv > 1e-4f ? mv : 1e-4f));
      }
      Serial.println("# SPECTRUM_END");
    }
  }
}
 
// ======================================================================
void setup() {
  Serial.setTxBufferSize(4096);
  Serial.begin(115200);
  delay(200);
 
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, HIGH);
  analogReadResolution(12);
  analogSetPinAttenuation(ADC_PIN, ADC_11db);
 
  bands[0].init("425-445", 425, 445);
  bands[1].init("490-510", 490, 510);
  bands[2].init("525-545", 525, 545);
  envK = 1.0f - expf(-1.0f / (SAMPLE_RATE * ENV_TAU_S));
  dcEst = analogRead(ADC_PIN);
  hp1.set(HP_CUTOFF, 0.5412f);   // Q values of a 4th-order Butterworth
  hp2.set(HP_CUTOFF, 1.3066f);
 
  for (int n = 0; n < N_BLOCK; n++) hannW[n] = 0.5f - 0.5f * cosf(2.0f * PI * n / (N_BLOCK - 1));
  float step = SAMPLE_RATE / N_BLOCK;
  for (float f = SCAN_LO; f <= SCAN_HI + 0.01f && nBins < MAX_BINS; f += step) {
    binFreq[nBins] = f;
    binCoeff[nBins] = 2.0f * cosf(2.0f * PI * f / SAMPLE_RATE);
    nBins++;
  }
 
  xTaskCreatePinnedToCore(analysisTask, "analysis", 8192, NULL, 1, &analysisHandle, 0);
  Serial.printf("# detection band %d (%s Hz)\n", activeBand + 1, bands[activeBand].name);
  Serial.println("# t_ms,peak_tx_hz,peak_tx_mV,peak_all_hz,peak_all_mV,rms_adc_mV,rms_opamp_mV,"
                 "env_425_445,env_490_510,env_525_545,active_band,beam_broken,adc_min,adc_max,missed");
  startCal(CAL_NOISE, 500);    // auto noise calibration at boot (beam blocked)
}
 
void loop() {
  static uint32_t tNext = micros();
  static uint32_t lastSerialMs = 0;
 
  while ((int32_t)(micros() - tNext) < 0) { }
  tNext += TS_US;
 
  // ---- sample ----
  int raw = analogRead(ADC_PIN);
 
  fillBuf[fillIdx++] = raw;
  if (fillIdx >= N_BLOCK) {
    readyBuf = fillBuf;
    fillBuf = (fillBuf == bufA) ? bufB : bufA;
    fillIdx = 0;
    if (analysisHandle) xTaskNotifyGive(analysisHandle);
  }
 
  // ---- band filters ----
  dcEst += 0.001f * (raw - dcEst);
  float x = hp2.process(hp1.process(raw - dcEst));   // drop everything below 160 Hz
  for (int i = 0; i < 3; i++) bands[i].update(x, envK);
 
  uint32_t now = millis();
 
  // ---- calibration ----
  if (calMode != CAL_NONE && (int32_t)(now - calStartMs) >= 0) {
    for (int i = 0; i < 3; i++) calAccum[i] += bands[i].env;
    calCount++;
    if (now - calStartMs >= 2000) {
      for (int i = 0; i < 3; i++) {
        float m = calAccum[i] / calCount;
        if (calMode == CAL_NOISE) noiseCal[i] = m; else sigCal[i] = m;
      }
      Serial.printf("# %s cal: band1=%.2f band2=%.2f band3=%.2f\n",
                    calMode == CAL_NOISE ? "NOISE" : "SIGNAL",
                    calAccum[0] / calCount, calAccum[1] / calCount, calAccum[2] / calCount);
      if (calMode == CAL_NOISE && !calibratedOnce) Serial.println("# ready - unblock the beam");
      calMode = CAL_NONE;
      calibratedOnce = true;
      recomputeThresholds();
    }
  }
 
  // ---- detection: hysteresis + debounce ----
  if (calibratedOnce) {
    float e = bands[activeBand].env;
    bool want = beamBroken;
    if (!beamBroken && e < thrOff) want = true;
    if ( beamBroken && e > thrOn)  want = false;
 
    if (want == beamBroken) {
      condSinceMs = now;
    } else if (now - condSinceMs >= DEBOUNCE_MS) {
      beamBroken = want;
      condSinceMs = now;
      digitalWrite(LED_PIN, beamBroken ? HIGH : LOW);
      Serial.printf("# %lu ms: beam %s\n", (unsigned long)now, beamBroken ? "BROKEN" : "PRESENT");
 
      if (beamBroken) {
        Serial.println("BREACH");
      } else {
        Serial.println("CLEAR");
      }
    }
  }
 
  if (now - lastSerialMs >= 50) { lastSerialMs = now; handleSerial(); }
 
  if ((int32_t)(micros() - tNext) > (int32_t)TS_US) { missed++; tNext = micros(); }
}
