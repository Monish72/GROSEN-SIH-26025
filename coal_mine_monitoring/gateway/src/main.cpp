// GROSEN: Dedicated ESP32 LoRa USB serial edge gateway firmware.

#include <Arduino.h>
#include <SPI.h>
#include <LoRa.h>
#include "config.h"

// Global telemetry counters and node timestamp tracking variables.
uint32_t total_lora_rx = 0;
uint32_t node1_rx_count = 0;
uint32_t node2_rx_count = 0;
unsigned long last_node1_seen = 0;
unsigned long last_node2_seen = 0;

// Initialize hardware serial, status indicator LED, and SX1278 LoRa radio receiver.
void setup() {
    Serial.begin(115200);
    delay(500);

    // Configure status indicator LED pin.
    pinMode(2, OUTPUT);
    digitalWrite(2, LOW);

    Serial.println();
    Serial.println("========================================================");
    Serial.println("  GROSEN - DEDICATED LORA GATEWAY");
    Serial.println("  Operating Mode: Ultra-Fast USB Serial Edge Bridge");
    Serial.println("========================================================");
    Serial.println();

    // Initialize SPI bus and LoRa transceiver pins.
    SPI.begin(LORA_SCK, LORA_MISO, LORA_MOSI, LORA_CS);
    LoRa.setPins(LORA_CS, LORA_RST, LORA_DIO0);

    if (LoRa.begin((long)LORA_FREQUENCY)) {
        Serial.printf("[OK] LoRa radio initialized @ %.1f MHz\n", LORA_FREQUENCY / 1E6);
    } else {
        Serial.println("[FAIL] LoRa initialization failed! Check SPI wires & power.");
        while (1) {
            digitalWrite(2, HIGH);
            delay(100);
            digitalWrite(2, LOW);
            delay(100);
        }
    }

    // Configure LoRa spreading factor, bandwidth, coding rate, and synchronization word.
    LoRa.setSpreadingFactor(LORA_SF);
    LoRa.setSignalBandwidth((long)LORA_BW);
    LoRa.setCodingRate4(LORA_CR);
    LoRa.setSyncWord(LORA_SYNC_WORD);
    LoRa.setPreambleLength(LORA_PREAMBLE);

    Serial.printf("[OK] Radio Config: SF=%d | BW=%.0f kHz | CR=4/%d | SyncWord=0x%02X\n",
                  LORA_SF, LORA_BW / 1000.0, LORA_CR, LORA_SYNC_WORD);
    Serial.println("[OK] Gateway ready. Listening for real-time LoRa sensor streams...");
    Serial.println("========================================================\n");

    // Blink onboard status LED to signal completed hardware initialization.
    for (int i = 0; i < 2; i++) {
        digitalWrite(2, HIGH); delay(100);
        digitalWrite(2, LOW); delay(100);
    }
}

// Poll SX1278 radio for incoming LoRa RF packets and stream to serial bridge.
void loop() {
    // Check radio buffer for newly arrived RF packet.
    int packetSize = LoRa.parsePacket();
    if (packetSize == 0) return;

    // Illuminate status LED during RF packet processing.
    digitalWrite(2, HIGH);

    // Extract packet payload bytes into local buffer.
    String raw = "";
    raw.reserve(64);
    while (LoRa.available()) {
        raw += (char)LoRa.read();
    }

    int rssi = LoRa.packetRssi();
    float snr = LoRa.packetSnr();
    total_lora_rx++;

    // Update packet reception counters and last seen timestamps per node ID.
    if (raw.startsWith("N1,")) {
        node1_rx_count++;
        last_node1_seen = millis();
    } else if (raw.startsWith("N2,")) {
        node2_rx_count++;
        last_node2_seen = millis();
    }

    // Stream formatted atomic telemetry line to USB serial monitor.
    Serial.printf("[PKT] %s|RSSI=%d|SNR=%.1f\n", raw.c_str(), rssi, snr);
    
    // Print human-readable reception statistics to serial monitor.
    Serial.printf("[RX] %s | RSSI: %d dBm | SNR: %.1f dB | Packets: %lu\n",
                  raw.startsWith("N1,") ? "NODE 1" : "NODE 2",
                  rssi, snr, (unsigned long)total_lora_rx);

    digitalWrite(2, LOW);
}
