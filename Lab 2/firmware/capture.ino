// Lab 2 capture sketch
// Records a burst of raw samples from A0 at a fixed rate and dumps them over serial,
// so analysis/capture_fft.py can plot them and find the frequency of whatever the
// photodiode is seeing (transmitter, lamp, phone flashlight, ...).
//
// Usage: open with analysis/capture_fft.py (it sends 'c' and reads the result).
// Manual use: Serial Monitor at 115200, type c and press Enter.
//
// Output format:
//   BEGIN <fs_hz> <num_samples>
//   <sample 0..1023>   (one per line)
//   ...
//   END

// Supporting firmware for classic ATmega328P Uno/Nano boards only.
// Primary team hardware must run receiver_esp32.ino instead.
#include <Arduino.h>
#if !defined(__AVR_ATmega328P__)
#error "capture.ino requires a classic ATmega328P Uno/Nano; use receiver_esp32.ino on ESP32"
#else

#ifndef cbi
#define cbi(sfr, bit) (_SFR_BYTE(sfr) &= ~_BV(bit))
#endif
#ifndef sbi
#define sbi(sfr, bit) (_SFR_BYTE(sfr) |= _BV(bit))
#endif

const int ANALOG_PIN = A0;

// 10 kHz lets you see anything up to 5 kHz. The Uno only has 2 KB of RAM,
// so samples are stored at 8 bits (plenty for finding frequencies).
const unsigned long CAPTURE_FS = 10000;
const int N_SAMPLES = 1200;            // 1200 samples at 10 kHz = 0.12 s, ~8 Hz resolution

uint8_t buf[N_SAMPLES];

void setup() {
  Serial.begin(115200);
  sbi(ADCSRA, ADPS2);   // fast ADC
  cbi(ADCSRA, ADPS1);
  cbi(ADCSRA, ADPS0);
  Serial.println("CAPTURE READY (send c)");
}

void capture() {
  const unsigned long ts = 1000000UL / CAPTURE_FS;
  unsigned long next = micros();
  for (int i = 0; i < N_SAMPLES; i++) {
    while ((long)(micros() - next) < 0) { }
    buf[i] = analogRead(ANALOG_PIN) >> 2;  // 10-bit -> 8-bit
    next += ts;
  }
  Serial.print("BEGIN ");
  Serial.print(CAPTURE_FS);
  Serial.print(" ");
  Serial.println(N_SAMPLES);
  for (int i = 0; i < N_SAMPLES; i++) {
    Serial.println((int)buf[i] << 2);      // back to the 0..1023 scale
  }
  Serial.println("END");
}

void loop() {
  if (Serial.available()) {
    char c = Serial.read();
    if (c == 'c' || c == 'C') capture();
  }
}

#endif // __AVR_ATmega328P__
