# GROSEN: Automated retry upload helper invoking PlatformIO flashing over COM7.
import subprocess
import time
import sys

print("=======================================================")
print("  PRESS AND HOLD THE 'BOOT' BUTTON ON THE ESP32 NOW!")
print("=======================================================")

for attempt in range(1, 6):
    print(f"\n[Attempt {attempt}/5] Attempting upload... (Keep holding BOOT button!)")
    res = subprocess.run([sys.executable, "-m", "platformio", "run", "--target", "upload", "--upload-port", "COM7"])
    if res.returncode == 0:
        print("\n=======================================================")
        print("  SUCCESS! SENSOR NODE 1 FLASHED AND READY!")
        print("=======================================================")
        sys.exit(0)
    time.sleep(1)

print("\nFailed to connect. Make sure to press and hold BOOT before upload starts.")
sys.exit(1)
