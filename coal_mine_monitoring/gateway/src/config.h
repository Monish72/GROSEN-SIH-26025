// GROSEN: Gateway configuration and LoRa radio parameters for edge forwarding.
#ifndef CONFIG_H
#define CONFIG_H

// Unique numerical identity for the gateway receiver.
#define GATEWAY_ID          0

// Local Wi-Fi network credentials for HTTP bridge fallback.
#define WIFI_SSID           "ACT FIBER"
#define WIFI_PASSWORD       "9962471188"

// Backend telemetry ingestion endpoint URL.
#define SERVER_URL          "http://192.168.0.3:8000/api/telemetry"

// Sub-second HTTP timeout in milliseconds for responsive transmission.
#define HTTP_TIMEOUT_MS     500

// Maximum HTTP POST retry attempts on failed transmission.
#define HTTP_MAX_RETRIES    0

// SPI bus hardware pin assignments for SX1278 LoRa transceiver.
#define LORA_SCK            18
#define LORA_MISO           19
#define LORA_MOSI           23
#define LORA_CS             5
#define LORA_RST            4
#define LORA_DIO0           26

// RF configuration parameters for LoRa modulation and packet reception.
#define LORA_FREQUENCY      433E6
#define LORA_SF             7
#define LORA_BW             125E3
#define LORA_CR             5
#define LORA_SYNC_WORD      0x34
#define LORA_TX_POWER       17
#define LORA_PREAMBLE       8

// Inactivity threshold in milliseconds before marking a sensor node offline.
#define NODE_TIMEOUT_MS     15000

// Number of sensor nodes tracked in local telemetry network.
#define NUM_SENSOR_NODES    2

// Wi-Fi reconnection retry delay and attempt limits.
#define WIFI_RETRY_DELAY_MS 5000
#define WIFI_MAX_RETRIES    20

#endif // CONFIG_H
