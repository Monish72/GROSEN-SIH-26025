// GROSEN: Sensor node hardware pinout and LoRa radio configuration.
#ifndef CONFIG_H
#define CONFIG_H

// Numerical sensor node identifier (1 for Node 1, 2 for Node 2).
#define NODE_ID             1

// String representation of node identifier matching backend topology.
#define NODE_ID_STR         (NODE_ID == 1 ? "NODE_01" : "NODE_02")

// Toggle sending fixed test metrics instead of live accelerometer data.
#define TEST_MODE           false

// I2C bus pin definitions and default address for MPU6050 sensor.
#define MPU6050_SDA         21
#define MPU6050_SCL         22
#define MPU6050_ADDR        0x68

// MPU6050 register addresses for power management, config, and data readout.
#define REG_PWR_MGMT_1      0x6B
#define REG_ACCEL_CONFIG     0x1C
#define REG_ACCEL_XOUT_H     0x3B
#define REG_TEMP_OUT_H       0x41
#define REG_WHO_AM_I         0x75

// Accelerometer dynamic range selection (0 = +/-2g, 16384 LSB/g).
#define ACCEL_RANGE         0
#define ACCEL_SCALE         16384.0

// SPI bus pin assignments for RA-02 SX1278 LoRa module.
#define LORA_SCK            18
#define LORA_MISO           19
#define LORA_MOSI           23
#define LORA_CS             5
#define LORA_RST            4
#define LORA_DIO0           26

// RF configuration parameters for 433 MHz LoRa transceiver.
#define LORA_FREQUENCY      433E6
#define LORA_SF             7
#define LORA_BW             125E3
#define LORA_CR             5
#define LORA_SYNC_WORD      0x34
#define LORA_TX_POWER       17
#define LORA_PREAMBLE       8

// Sampling timing and transmission buffer size parameters.
#define SAMPLE_INTERVAL_MS  40
#define SAMPLES_PER_TX      5
#define CALIBRATION_SAMPLES 25

// Transmission time-slot offset in milliseconds to prevent packet collisions.
#define TX_SLOT_OFFSET_MS   ((NODE_ID - 1) * 90)

// Fixed test mode values for bench validation without physical sensor.
#define TEST_TILT_PITCH     1.20
#define TEST_TILT_ROLL      0.50
#define TEST_TILT_TOTAL     1.30
#define TEST_VIB_RMS        0.03
#define TEST_VIB_PEAK       0.15
#define TEST_TEMP           30.0

#endif // CONFIG_H
