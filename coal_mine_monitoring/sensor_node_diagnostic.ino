// GROSEN: Sensor node all-in-one hardware tester for MPU6050 accelerometer and RA-02 LoRa.

#include <Wire.h>
#include <SPI.h>
#include <LoRa.h>

// Node ID, pinouts, and hardware register configuration definitions.
#define NODE_ID             1

#define MPU_SDA             21
#define MPU_SCL             22
#define MPU_ADDR_DEFAULT    0x68

#define LORA_SCK            18
#define LORA_MISO           19
#define LORA_MOSI           23
#define LORA_CS             5
#define LORA_RST            4
#define LORA_DIO0           26
#define LORA_FREQ           433E6

#define LED_PIN             2

#define REG_PWR_MGMT_1      0x6B
#define REG_ACCEL_CONFIG    0x1C
#define REG_ACCEL_XOUT_H    0x3B
#define REG_WHO_AM_I        0x75

// Detection flags, address tracker, and packet sequence counter.
bool mpu_detected = false;
bool lora_detected = false;
uint8_t mpu_addr = MPU_ADDR_DEFAULT;
uint32_t packet_counter = 0;

float base_ax = 0.0, base_ay = 0.0, base_az = 1.0;
bool is_calibrated = false;

// Probe I2C addresses 0x68 and 0x69 and initialize MPU6050 in +/-2g mode.
bool initMPU6050() {
    uint8_t possible_addrs[] = {0x68, 0x69};
    
    Wire.begin(MPU_SDA, MPU_SCL);
    Wire.setClock(100000);
    delay(50);

    for (uint8_t addr : possible_addrs) {
        Wire.beginTransmission(addr);
        if (Wire.endTransmission(true) == 0) {
            mpu_addr = addr;

            // Clear sleep bit to activate MPU6050.
            Wire.beginTransmission(mpu_addr);
            Wire.write(REG_PWR_MGMT_1);
            Wire.write(0x00);
            Wire.endTransmission(true);
            delay(30);

            // Configure accelerometer full-scale range to +/-2g.
            Wire.beginTransmission(mpu_addr);
            Wire.write(REG_ACCEL_CONFIG);
            Wire.write(0x00);
            Wire.endTransmission(true);
            delay(10);

            // Verify sensor identity via WHO_AM_I register.
            Wire.beginTransmission(mpu_addr);
            Wire.write(REG_WHO_AM_I);
            Wire.endTransmission(false);
            Wire.requestFrom((uint8_t)mpu_addr, (uint8_t)1);
            uint8_t who = Wire.available() ? Wire.read() : 0x00;

            Serial.printf("  [OK] MPU6050 detected at I2C address 0x%02X (WHO_AM_I: 0x%02X)\n", mpu_addr, who);
            return true;
        }
    }
    return false;
}

// Read 3-axis acceleration and temperature registers in a single atomic I2C burst.
bool readMPU6050(float &ax, float &ay, float &az, float &temp_c) {
    if (!mpu_detected) return false;

    Wire.beginTransmission(mpu_addr);
    Wire.write(REG_ACCEL_XOUT_H);
    if (Wire.endTransmission(false) != 0) {
        Wire.beginTransmission(mpu_addr);
        Wire.write(REG_ACCEL_XOUT_H);
        if (Wire.endTransmission(true) != 0) return false;
    }

    Wire.requestFrom((uint8_t)mpu_addr, (uint8_t)8);
    if (Wire.available() < 8) return false;

    int16_t raw_ax   = (Wire.read() << 8) | Wire.read();
    int16_t raw_ay   = (Wire.read() << 8) | Wire.read();
    int16_t raw_az   = (Wire.read() << 8) | Wire.read();
    int16_t raw_temp = (Wire.read() << 8) | Wire.read();

    ax = (float)raw_ax / 16384.0f;
    ay = (float)raw_ay / 16384.0f;
    az = (float)raw_az / 16384.0f;
    temp_c = ((float)raw_temp / 340.0f) + 36.53f;

    return true;
}

// Initialize serial monitor, probe MPU6050, and initialize SX1278 LoRa radio.
void setup() {
    Serial.begin(115200);
    delay(1500);

    pinMode(LED_PIN, OUTPUT);
    digitalWrite(LED_PIN, LOW);

    Serial.println("\n========================================================");
    Serial.printf("  GROSEN - NODE %d DIAGNOSTIC TEST\n", NODE_ID);
    Serial.println("========================================================");

    // Probe MPU6050 on I2C bus.
    Serial.println("\n[1/2] Probing MPU6050 on I2C (SDA=21, SCL=22)...");
    mpu_detected = initMPU6050();
    if (!mpu_detected) {
        Serial.println("  [FAIL] MPU6050 NOT DETECTED!");
        Serial.println("  --> Check Wiring:");
        Serial.println("      1. VCC  -> Connect to VIN (5V) pin (not 3V3).");
        Serial.println("      2. GND  -> GND");
        Serial.println("      3. SDA  -> GPIO 21");
        Serial.println("      4. SCL  -> GPIO 22");
        Serial.println("      5. AD0  -> GND");
        Serial.println("      6. Check if RED power LED on GY-521 is lit.");
    }

    // Initialize SPI bus and configure SX1278 LoRa radio.
    Serial.println("\n[2/2] Initializing RA-02 LoRa on SPI (SCK=18, MISO=19, MOSI=23, CS=5, RST=4, DIO0=26)...");
    SPI.begin(LORA_SCK, LORA_MISO, LORA_MOSI, LORA_CS);
    LoRa.setPins(LORA_CS, LORA_RST, LORA_DIO0);

    if (LoRa.begin((long)LORA_FREQ)) {
        lora_detected = true;
        LoRa.setSpreadingFactor(7);
        LoRa.setSignalBandwidth(125E3);
        LoRa.setCodingRate4(5);
        LoRa.setSyncWord(0x34);
        LoRa.setTxPower(17);
        Serial.println("  [OK] RA-02 LoRa radio initialized successfully @ 433 MHz!");
    } else {
        Serial.println("  [FAIL] LoRa radio failed to initialize!");
        Serial.println("  --> Check SPI wires: SCK(18), MISO(19), MOSI(23), CS(5), RST(4), DIO0(26), VCC(3.3V ONLY!)");
    }

    Serial.println("\n========================================================");
    Serial.println("  STARTING REAL-TIME SENSOR STREAM (Every 1 Second)...");
    Serial.println("  Gently tilt or tap the MPU6050 to see live values shift!");
    Serial.println("========================================================\n");
}

// Sample accelerometer, compute 3D tilt angles, and transmit packets via LoRa.
void loop() {
    float ax = 0.0, ay = 0.0, az = 1.0, temp_c = 0.0;

    // Retry MPU6050 initialization if reconnected on the fly.
    if (!mpu_detected) {
        mpu_detected = initMPU6050();
    }

    bool read_success = readMPU6050(ax, ay, az, temp_c);

    if (read_success) {
        // Calculate pitch, roll, and total 3D tilt angle in degrees.
        float pitch_deg = atan2(ax, sqrt(ay * ay + az * az)) * 180.0f / PI;
        float roll_deg  = atan2(ay, sqrt(ax * ax + az * az)) * 180.0f / PI;
        float total_tilt = atan2(sqrt(ax * ax + ay * ay), az) * 180.0f / PI;

        // Calculate peak dynamic vibration deviation from 1g baseline.
        float mag = sqrt(ax * ax + ay * ay + az * az);
        float vib_peak_g = abs(mag - 1.0f);

        // Serialize measurements into standard CSV packet string.
        char packet[128];
        snprintf(packet, sizeof(packet), "N%d,%lu,%.3f,%.3f,%.3f,%.4f,%.4f,%.1f",
                 NODE_ID, (unsigned long)packet_counter,
                 pitch_deg, roll_deg, total_tilt,
                 vib_peak_g * 0.6f, vib_peak_g, temp_c);

        // Transmit packet over LoRa radio and blink onboard LED.
        bool tx_ok = false;
        if (lora_detected) {
            LoRa.beginPacket();
            LoRa.print(packet);
            LoRa.endPacket();
            tx_ok = true;

            digitalWrite(LED_PIN, HIGH);
            delay(30);
            digitalWrite(LED_PIN, LOW);
        }

        // Print telemetry summary to serial monitor.
        Serial.printf("[NODE %d | TX #%lu]\n", NODE_ID, (unsigned long)packet_counter);
        Serial.printf("  ├─ Tilt Pitch : %+06.2f deg\n", pitch_deg);
        Serial.printf("  ├─ Tilt Roll  : %+06.2f deg\n", roll_deg);
        Serial.printf("  ├─ Total Tilt :  %05.2f deg\n", total_tilt);
        Serial.printf("  ├─ Vibration  :  %06.4f g  (Mag: %.3fg)\n", vib_peak_g, mag);
        Serial.printf("  ├─ Temperature:  %05.1f °C\n", temp_c);
        Serial.printf("  ├─ LoRa Packet:  %s\n", packet);
        Serial.printf("  └─ LoRa TX    :  %s\n", tx_ok ? "SENT [✓]" : "RADIO OFFLINE [X]");
        Serial.println("--------------------------------------------------------");

        packet_counter++;
    } else {
        Serial.printf("[NODE %d ERROR] MPU6050 not communicating on I2C! Re-trying...\n", NODE_ID);
    }

    delay(1000);
}
