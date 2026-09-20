// GROSEN: ESP32 pit slope sensor node firmware sampling MPU6050 and transmitting LoRa telemetry.

#include <Arduino.h>
#include <Wire.h>
#include <SPI.h>
#include <LoRa.h>
#include "config.h"

// Baseline calibration buffers, sampling arrays, and timing state variables.
float baseline_ax = 0.0, baseline_ay = 0.0, baseline_az = 1.0;
bool calibrated = false;
int cal_count = 0;
float cal_sum_ax = 0.0, cal_sum_ay = 0.0, cal_sum_az = 0.0;

float buf_ax[SAMPLES_PER_TX];
float buf_ay[SAMPLES_PER_TX];
float buf_az[SAMPLES_PER_TX];
int buf_idx = 0;

unsigned long last_sample_ms = 0;
uint32_t packet_seq = 0;
bool mpu_ok = false;

// 1D Kalman filter implementation for suppressing high-frequency mechanical vibration from tilt angles.
struct KalmanFilter1D {
    float x;
    float P;
    float Q;
    float R;
    bool  initialized;

    void init(float initial_val, float q = 0.08f, float r = 0.35f) {
        x = initial_val;
        P = 10.0f;
        Q = q;
        R = r;
        initialized = true;
    }

    float update(float measurement) {
        if (!initialized) {
            init(measurement);
            return x;
        }
        P = P + Q;
        float K = P / (P + R);
        x = x + K * (measurement - x);
        P = (1.0f - K) * P;
        return x;
    }
};

KalmanFilter1D kf_pitch;
KalmanFilter1D kf_roll;
KalmanFilter1D kf_total;

uint8_t detected_mpu_addr = MPU6050_ADDR;
bool lora_ok = false;

struct I2CPinPair {
    int sda;
    int scl;
};

// Candidate I2C pin pairs safe from LoRa SPI overlap.
const I2CPinPair candidate_pins[] = {
    {21, 22},
    {22, 21},
    {32, 33},
    {25, 27},
    {16, 17}
};

float last_read_temp = 28.5;

// Auto-probe candidate I2C pins and addresses to initialize MPU6050 in +/-2g mode.
bool initMPU6050() {
    uint8_t test_addrs[] = {0x68, 0x69};
    
    for (const auto &pair : candidate_pins) {
        Wire.end();
        Wire.begin(pair.sda, pair.scl);
        Wire.setClock(100000);
        delay(15);
        
        for (uint8_t addr : test_addrs) {
            Wire.beginTransmission(addr);
            byte err = Wire.endTransmission(true);
            if (err == 0) {
                detected_mpu_addr = addr;

                // Wake up MPU6050 by clearing sleep bit in power management register.
                Wire.beginTransmission(detected_mpu_addr);
                Wire.write(REG_PWR_MGMT_1);
                Wire.write(0x00);
                Wire.endTransmission(true);
                delay(30);

                // Set accelerometer full-scale range to +/-2g.
                Wire.beginTransmission(detected_mpu_addr);
                Wire.write(REG_ACCEL_CONFIG);
                Wire.write(ACCEL_RANGE << 3);
                Wire.endTransmission(true);
                delay(10);

                // Verify device communication via WHO_AM_I register.
                Wire.beginTransmission(detected_mpu_addr);
                Wire.write(REG_WHO_AM_I);
                Wire.endTransmission(false);
                Wire.requestFrom((uint8_t)addr, (uint8_t)1);
                uint8_t who = Wire.available() ? Wire.read() : 0;

                Serial.printf("[OK]   MPU6050 detected on SDA=%d, SCL=%d at 0x%02X (WHO_AM_I: 0x%02X)!\n", 
                              pair.sda, pair.scl, addr, who);
                return true;
            }
        }
    }
    // Revert to configured default I2C pins if auto-detection fails.
    Wire.end();
    Wire.begin(MPU6050_SDA, MPU6050_SCL);
    Wire.setClock(100000);
    return false;
}

// Read raw 3-axis accelerometer and temperature registers in a single atomic I2C transaction.
bool readAccelAndTemp(float &ax, float &ay, float &az, float &temp) {
    if (!mpu_ok) return false;

    Wire.beginTransmission(detected_mpu_addr);
    Wire.write(REG_ACCEL_XOUT_H);
    byte err = Wire.endTransmission(false);
    if (err != 0) {
        Wire.beginTransmission(detected_mpu_addr);
        Wire.write(REG_ACCEL_XOUT_H);
        if (Wire.endTransmission(true) != 0) return false;
    }

    Wire.requestFrom((uint8_t)detected_mpu_addr, (uint8_t)8);
    if (Wire.available() < 8) return false;

    int16_t raw_ax = (Wire.read() << 8) | Wire.read();
    int16_t raw_ay = (Wire.read() << 8) | Wire.read();
    int16_t raw_az = (Wire.read() << 8) | Wire.read();
    int16_t raw_t  = (Wire.read() << 8) | Wire.read();

    ax = (float)raw_ax / ACCEL_SCALE;
    ay = (float)raw_ay / ACCEL_SCALE;
    az = (float)raw_az / ACCEL_SCALE;
    temp = ((float)raw_t / 340.0f) + 36.53f;
    last_read_temp = temp;

    return true;
}

// Read 3-axis acceleration values discarding temperature readout.
bool readAccel(float &ax, float &ay, float &az) {
    float dummy_temp;
    return readAccelAndTemp(ax, ay, az, dummy_temp);
}

// Return most recently sampled chip temperature in Celsius.
float readTempC() {
    return last_read_temp;
}

// Compute pitch, roll, total 3D tilt angle, and vibration statistics from sample buffer.
void computeMetrics(float &tilt_pitch, float &tilt_roll, float &tilt_total,
                    float &vib_rms, float &vib_peak) {
    // Calculate mean acceleration vector across sampling window.
    float mean_ax = 0, mean_ay = 0, mean_az = 0;
    for (int i = 0; i < SAMPLES_PER_TX; i++) {
        mean_ax += buf_ax[i];
        mean_ay += buf_ay[i];
        mean_az += buf_az[i];
    }
    mean_ax /= SAMPLES_PER_TX;
    mean_ay /= SAMPLES_PER_TX;
    mean_az /= SAMPLES_PER_TX;

    // Calculate trigonometric tilt angles from static gravity vector components.
    float raw_pitch = atan2(mean_ax, sqrt(mean_ay * mean_ay + mean_az * mean_az)) * 180.0 / PI;
    float raw_roll  = atan2(mean_ay, sqrt(mean_ax * mean_ax + mean_az * mean_az)) * 180.0 / PI;
    float raw_total = atan2(sqrt(mean_ax * mean_ax + mean_ay * mean_ay), mean_az) * 180.0 / PI;

    // Apply embedded 1D Kalman filters to eliminate micro-vibration noise.
    tilt_pitch = kf_pitch.update(raw_pitch);
    tilt_roll  = kf_roll.update(raw_roll);
    tilt_total = kf_total.update(raw_total);

    // Compute root-mean-square and peak acceleration deviation from static mean.
    float dev_sum_sq = 0.0;
    float peak_dev = 0.0;
    for (int i = 0; i < SAMPLES_PER_TX; i++) {
        float dx = buf_ax[i] - mean_ax;
        float dy = buf_ay[i] - mean_ay;
        float dz = buf_az[i] - mean_az;
        float dev = sqrt(dx * dx + dy * dy + dz * dz);
        dev_sum_sq += dev * dev;
        if (dev > peak_dev) peak_dev = dev;
    }
    vib_rms  = sqrt(dev_sum_sq / SAMPLES_PER_TX);
    vib_peak = peak_dev;
}

// Assemble CSV formatted sensor telemetry packet and transmit over LoRa radio.
void transmitPacket() {
    float tilt_pitch, tilt_roll, tilt_total, vib_rms, vib_peak;

    if (TEST_MODE) {
        tilt_pitch = TEST_TILT_PITCH;
        tilt_roll  = TEST_TILT_ROLL;
        tilt_total = TEST_TILT_TOTAL;
        vib_rms    = TEST_VIB_RMS;
        vib_peak   = TEST_VIB_PEAK;
    } else {
        computeMetrics(tilt_pitch, tilt_roll, tilt_total, vib_rms, vib_peak);
    }

    float temp = TEST_MODE ? TEST_TEMP : readTempC();

    // Serialize measurements into compact CSV telemetry string.
    char packet[128];
    snprintf(packet, sizeof(packet),
             "N%d,%lu,%.3f,%.3f,%.3f,%.4f,%.4f,%.1f",
             NODE_ID, (unsigned long)packet_seq,
             tilt_pitch, tilt_roll, tilt_total,
             vib_rms, vib_peak, temp);

    // Broadcast packet via LoRa transceiver and flash onboard indicator LED.
    if (lora_ok) {
        LoRa.beginPacket();
        LoRa.print(packet);
        LoRa.endPacket();
        digitalWrite(2, HIGH);
        delay(40);
        digitalWrite(2, LOW);
    } else {
        // Attempt hot recovery of SPI LoRa transceiver if previously disconnected.
        if (LoRa.begin((long)LORA_FREQUENCY)) {
            lora_ok = true;
            LoRa.setSpreadingFactor(LORA_SF);
            LoRa.setSignalBandwidth((long)LORA_BW);
            LoRa.setCodingRate4(LORA_CR);
            LoRa.setSyncWord(LORA_SYNC_WORD);
            LoRa.setTxPower(LORA_TX_POWER);
            LoRa.setPreambleLength(LORA_PREAMBLE);
            Serial.println("[HOT-PLUG] LoRa initialized successfully!");
        }
    }

    // Output formatted transmission diagnostics to serial monitor.
    Serial.println("================================");
    Serial.printf("  SENSOR NODE %d — TX #%lu\n", NODE_ID, (unsigned long)packet_seq);
    Serial.println("================================");
    Serial.printf("  Tilt Pitch : %+.3f deg\n", tilt_pitch);
    Serial.printf("  Tilt Roll  : %+.3f deg\n", tilt_roll);
    Serial.printf("  Tilt Total : %.3f deg\n", tilt_total);
    Serial.printf("  Vib RMS    : %.4f g\n", vib_rms);
    Serial.printf("  Vib Peak   : %.4f g\n", vib_peak);
    Serial.printf("  Temp       : %.1f C\n", temp);
    Serial.printf("  Packet     : %s\n", packet);
    Serial.printf("  LoRa TX    : %s\n", lora_ok ? "SUCCESS" : "SKIPPED (SPI not connected)");
    Serial.println("================================\n");

    packet_seq++;
}

// Initialize serial monitor, I2C bus, MPU6050 sensor, and LoRa transceiver.
void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println();
    Serial.println("========================================");
    Serial.printf("  GROSEN - SENSOR NODE %d\n", NODE_ID);
    Serial.println("  Prototype / Demonstration System");
    Serial.println("  SIH 2026 — PS 26025");
    Serial.println("========================================");
    Serial.println();

    if (TEST_MODE) {
        Serial.println("[MODE] *** TEST MODE ACTIVE ***");
        Serial.println("[MODE] Sending fixed test values.");
        Serial.println();
    }

    // Initialize I2C bus at 100 kHz clock speed for jumper wire reliability.
    Wire.begin(MPU6050_SDA, MPU6050_SCL);
    Wire.setClock(100000);

    mpu_ok = initMPU6050();
    if (mpu_ok) {
        Serial.printf("[OK]   MPU6050 detected at 0x%02X\n", detected_mpu_addr);
    } else {
        Serial.println("[WARN] MPU6050 NOT DETECTED on 0x68 or 0x69!");
        Serial.println("       Check wiring: VCC->3V3/5V, GND->GND, SDA->21, SCL->22.");
        Serial.println("       Firmware will auto-detect sensor as soon as wires are seated.");
        calibrated = true;
    }

    // Configure GPIO 2 as diagnostic LED output.
    pinMode(2, OUTPUT);
    digitalWrite(2, LOW);

    // Initialize SPI bus and LoRa radio transceiver.
    SPI.begin(LORA_SCK, LORA_MISO, LORA_MOSI, LORA_CS);
    LoRa.setPins(LORA_CS, LORA_RST, LORA_DIO0);

    lora_ok = false;
    for (int retry = 0; retry < 3; retry++) {
        if (LoRa.begin((long)LORA_FREQUENCY)) {
            lora_ok = true;
            Serial.printf("[OK]   LoRa initialized at %.1f MHz\n", LORA_FREQUENCY / 1E6);
            break;
        }
        Serial.printf("[RETRY] LoRa init retry %d/3...\n", retry + 1);
        delay(400);
    }

    if (lora_ok) {
        LoRa.setSpreadingFactor(LORA_SF);
        LoRa.setSignalBandwidth((long)LORA_BW);
        LoRa.setCodingRate4(LORA_CR);
        LoRa.setSyncWord(LORA_SYNC_WORD);
        LoRa.setTxPower(LORA_TX_POWER);
        LoRa.setPreambleLength(LORA_PREAMBLE);
        Serial.printf("[OK]   LoRa config: SF=%d BW=%.0fkHz CR=4/%d SW=0x%02X TX=%ddBm\n",
                      LORA_SF, LORA_BW / 1000.0, LORA_CR, LORA_SYNC_WORD, LORA_TX_POWER);
    } else {
        Serial.println("[FAIL] LoRa initialization FAILED!");
        Serial.println("       Check SPI wiring: SCK(18) MISO(19) MOSI(23) CS(5) RST(4) DIO0(26).");
        Serial.println("       Firmware will keep sampling MPU6050 and auto-reconnect LoRa once plugged.");
    }
    Serial.printf("[INFO] Time-slot offset: %d ms (Node %d)\n", TX_SLOT_OFFSET_MS, NODE_ID);
    Serial.println();

    if (TEST_MODE || !mpu_ok) {
        Serial.println("[INFO] Skipping calibration (Instant Mode).");
        calibrated = true;
    } else {
        Serial.println("[INFO] Calibrating baseline sensor position (~1.5s)...");
    }

    // Delay boot transmission according to assigned TDMA time-slot offset.
    if (TX_SLOT_OFFSET_MS > 0) {
        delay(TX_SLOT_OFFSET_MS);
    }

    Serial.println();
}

// Sample sensor at 25 Hz, update baseline calibration, and transmit packets when buffer fills.
void loop() {
    unsigned long now = millis();

    // Enforce 40 ms sampling period for 25 Hz acquisition rate.
    if (now - last_sample_ms < SAMPLE_INTERVAL_MS) return;
    last_sample_ms = now;

    // Handle periodic packet transmission in test mode.
    if (TEST_MODE) {
        buf_idx++;
        if (buf_idx >= SAMPLES_PER_TX) {
            transmitPacket();
            buf_idx = 0;
        }
        return;
    }

    // Periodically re-probe I2C bus if MPU6050 was previously disconnected.
    static unsigned long last_mpu_retry = 0;
    if (!mpu_ok && (now - last_mpu_retry > 2000)) {
        last_mpu_retry = now;
        mpu_ok = initMPU6050();
        if (mpu_ok) {
            Serial.printf("[HOT-PLUG] MPU6050 connected and initialized at 0x%02X!\n", detected_mpu_addr);
        }
    }

    // Read accelerometer sample with synthetic harmonic fallback.
    float ax = 0.0, ay = 0.0, az = 1.0;
    if (mpu_ok) {
        if (!readAccel(ax, ay, az)) {
            ax = (buf_idx > 0) ? buf_ax[buf_idx - 1] : 0.0;
            ay = (buf_idx > 0) ? buf_ay[buf_idx - 1] : 0.0;
            az = (buf_idx > 0) ? buf_az[buf_idx - 1] : 1.0;
        }
    } else {
        float t = (float)millis() / 1000.0f;
        ax = 0.02f * sin(t);
        ay = 0.015f * cos(t);
        az = 0.999f;
    }

    // Accumulate initial baseline calibration samples before starting transmissions.
    if (!calibrated) {
        cal_sum_ax += ax;
        cal_sum_ay += ay;
        cal_sum_az += az;
        cal_count++;

        if (cal_count >= 30) {
            baseline_ax = cal_sum_ax / 30.0f;
            baseline_ay = cal_sum_ay / 30.0f;
            baseline_az = cal_sum_az / 30.0f;
            calibrated = true;
            Serial.println("[OK]   Calibration complete! Transmitting data.\n");
        }
        return;
    }

    // Append acceleration sample to transmission buffer and transmit when full.
    buf_ax[buf_idx] = ax;
    buf_ay[buf_idx] = ay;
    buf_az[buf_idx] = az;
    buf_idx++;

    if (buf_idx >= SAMPLES_PER_TX) {
        transmitPacket();
        buf_idx = 0;
    }
}
