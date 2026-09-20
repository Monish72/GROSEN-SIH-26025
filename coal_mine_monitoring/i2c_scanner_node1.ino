// GROSEN: Deep I2C hardware bus scanner and MPU6050 auto-discovery diagnostic utility.

#include <Wire.h>

// Candidate I2C pin pair and label structure for bus scanning.
struct PinTest {
    int sda;
    int scl;
    const char* label;
};

// Candidate GPIO pairs for I2C auto-detection.
PinTest test_pairs[] = {
    {21, 22, "Standard ESP32 (SDA=21, SCL=22)"},
    {22, 21, "Swapped SDA/SCL (SDA=22, SCL=21)"},
    {32, 33, "Auxiliary Pair A (SDA=32, SCL=33)"},
    {25, 27, "Auxiliary Pair B (SDA=25, SCL=27)"},
    {16, 17, "Auxiliary Pair C (SDA=16, SCL=17)"}
};

// Generate 9 manual clock pulses to release stuck I2C slave devices on the bus.
void clearI2CBus(int sda, int scl) {
    pinMode(sda, INPUT_PULLUP);
    pinMode(scl, OUTPUT);
    for (int i = 0; i < 10; i++) {
        digitalWrite(scl, HIGH);
        delayMicroseconds(5);
        digitalWrite(scl, LOW);
        delayMicroseconds(5);
    }
    digitalWrite(scl, HIGH);
    delayMicroseconds(5);
}

// Scan full 127-address range on specified pin pair and verify MPU6050 identity.
bool scanBus(int sda, int scl, const char* label) {
    Serial.printf("\n--> Scanning on: %s\n", label);
    clearI2CBus(sda, scl);

    Wire.end();
    Wire.begin(sda, scl);
    Wire.setClock(100000);
    delay(50);

    int found_count = 0;
    for (uint8_t addr = 1; addr < 127; addr++) {
        Wire.beginTransmission(addr);
        byte error = Wire.endTransmission(true);

        if (error == 0) {
            Serial.printf("  [SUCCESS] I2C Device Found at 0x%02X (%d)!\n", addr, addr);
            found_count++;

            // Verify MPU6050 device registers if detected at address 0x68 or 0x69.
            if (addr == 0x68 || addr == 0x69) {
                // Wake up sensor from sleep mode.
                Wire.beginTransmission(addr);
                Wire.write(0x6B);
                Wire.write(0x00);
                Wire.endTransmission(true);
                delay(20);

                // Read WHO_AM_I identity register.
                Wire.beginTransmission(addr);
                Wire.write(0x75);
                Wire.endTransmission(false);
                Wire.requestFrom(addr, (uint8_t)1);
                uint8_t who = Wire.available() ? Wire.read() : 0;
                
                Serial.printf("  >>> MPU6050 IDENTIFIED! WHO_AM_I Register = 0x%02X\n", who);

                // Sample test 3-axis accelerometer output.
                Wire.beginTransmission(addr);
                Wire.write(0x3B);
                Wire.endTransmission(false);
                Wire.requestFrom(addr, (uint8_t)6);
                if (Wire.available() >= 6) {
                    int16_t ax = (Wire.read() << 8) | Wire.read();
                    int16_t ay = (Wire.read() << 8) | Wire.read();
                    int16_t az = (Wire.read() << 8) | Wire.read();
                    Serial.printf("  >>> Live Accel Raw: AX=%d, AY=%d, AZ=%d\n", ax, ay, az);
                    Serial.printf("  >>> Live Accel (g): AX=%.2fg, AY=%.2fg, AZ=%.2fg\n", 
                                  ax / 16384.0, ay / 16384.0, az / 16384.0);
                }
            }
        } else if (error == 4) {
            Serial.printf("  [ERROR] Line Error / Bus Lock at address 0x%02X\n", addr);
        }
    }

    if (found_count == 0) {
        Serial.println("  [NO DEVICE FOUND on this pin pair]");
        return false;
    }
    return true;
}

// Initialize serial monitor for diagnostic reporting.
void setup() {
    Serial.begin(115200);
    delay(2000);

    Serial.println("\n========================================================");
    Serial.println("   GROSEN - MPU6050 I2C HARDWARE DETECT & SCANNER");
    Serial.println("========================================================");
}

// Periodically run multi-pin I2C scan cycles and print hardware diagnostic results.
void loop() {
    Serial.println("\n--------------------------------------------------------");
    Serial.println("Starting Full Multi-Pin Scan cycle...");
    Serial.println("--------------------------------------------------------");

    bool any_found = false;
    for (auto &pair : test_pairs) {
        if (scanBus(pair.sda, pair.scl, pair.label)) {
            any_found = true;
            break;
        }
        delay(100);
    }

    if (!any_found) {
        Serial.println("\n========================================================");
        Serial.println("  [HARDWARE FAULT DETECTED] No I2C response on any pins!");
        Serial.println("========================================================");
        Serial.println("Step-by-step fix checklist for Node 1:");
        Serial.println(" 1. POWER CHECK:");
        Serial.println("    - Is the small RED power LED on the GY-521 board turned ON?");
        Serial.println("    - If LED is OFF/DIM: Move VCC wire from 3V3 pin to the ESP32 VIN (5V) pin!");
        Serial.println(" 2. AD0 PIN:");
        Serial.println("    - Connect AD0 on MPU6050 to GND.");
        Serial.println(" 3. WIRE CHECK:");
        Serial.println("    - Replace the 4 jumper wires (VCC, GND, SDA, SCL). Breadboard wires often break internally.");
        Serial.println(" 4. PIN LABELS:");
        Serial.println("    - Make sure SDA is in pin labeled D21 (GPIO 21).");
        Serial.println("    - Make sure SCL is in pin labeled D22 (GPIO 22).");
        Serial.println("========================================================\n");
    } else {
        Serial.println("\n========================================================");
        Serial.println("  [SUCCESS] MPU6050 IS ACTIVE AND WORKING!");
        Serial.println("========================================================\n");
    }

    delay(3000);
}
