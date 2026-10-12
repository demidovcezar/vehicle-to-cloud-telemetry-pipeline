import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DATA_PATH = BASE_DIR / "data" / "raw" / "telemetry.jsonl"

VEHICLES = [f"VEHICLE_{i:02d}" for i in range(1, 6)]


class VehicleState:

    def __init__(self, vehicle_id: str):
        self.vehicle_id = vehicle_id
        self.speed = 0.0
        self.coolant_temp = random.uniform(25.0, 35.0)
        self.mode = "IDLE"
        self.ticks_in_mode = 0

    def update_physics(self) -> None:
        if self.ticks_in_mode <= 0:
            self.mode = random.choice(["ACCEL", "CRUISE", "DECEL", "IDLE"])
            self.ticks_in_mode = random.randint(6, 24)

        self.ticks_in_mode -= 1

        if self.mode == "ACCEL":
            self.speed = min(130.0, self.speed + random.uniform(2.0, 4.5))
        elif self.mode == "DECEL":
            self.speed = max(0.0, self.speed - random.uniform(3.0, 6.0))
        elif self.mode == "CRUISE":
            self.speed = max(40.0, min(125.0, self.speed + random.uniform(-1.5, 1.5)))
        elif self.mode == "IDLE":
            self.speed = max(0.0, self.speed - 3.0)

        if self.speed > 0:
            self.rpm = int(850 + (self.speed * 20) + random.uniform(-60, 60))
        else:
            self.rpm = random.randint(750, 820)

        if self.speed > 0 and self.coolant_temp < 92.0:
            self.coolant_temp += random.uniform(0.1, 0.3)
        elif self.speed == 0 and self.coolant_temp > 82.0:
            self.coolant_temp -= random.uniform(0.05, 0.15)

        self.battery_voltage = random.uniform(13.8, 14.3) if self.rpm > 1000 else random.uniform(12.3, 12.6)


def apply_sensor_anomalies(record: dict) -> dict:
    if random.random() < 0.01:
        record["speed_kmh"] = None
    if random.random() < 0.01:
        record["coolant_temp_c"] = None
    if random.random() < 0.01:
        record["battery_voltage"] = None

    if random.random() < 0.01 and record["speed_kmh"] is not None:
        record["speed_kmh"] = random.choice([-15.0, 240.0])
    if random.random() < 0.01 and record["coolant_temp_c"] is not None:
        record["coolant_temp_c"] = random.choice([-30.0, 150.0])

    if random.random() < 0.015:
        dtc = random.choice(["P0217", "P0117", "P0300"])
        record["diagnostic_code"] = dtc
        if dtc == "P0217" and record["coolant_temp_c"] is not None:
            record["coolant_temp_c"] = round(random.uniform(107.0, 118.0), 1)

    return record


def generate_telemetry_data(records_per_vehicle: int = 2000) -> None:
    RAW_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    start_time = datetime.now(timezone.utc) - timedelta(days=1)
    total_written = 0

    print(f"[generator] Generating telemetry data for {len(VEHICLES)} vehicles...")

    with open(RAW_DATA_PATH, "w", encoding="utf-8") as f:
        for v_id in VEHICLES:
            vehicle = VehicleState(v_id)
            current_time = start_time

            for step in range(records_per_vehicle):
                current_time += timedelta(seconds=5)
                vehicle.update_physics()

                telemetry_frame = {
                    "event_id": f"{v_id}_{step:05d}",
                    "vehicle_id": v_id,
                    "timestamp": current_time.isoformat(),
                    "speed_kmh": round(vehicle.speed, 1),
                    "engine_rpm": vehicle.rpm,
                    "coolant_temp_c": round(vehicle.coolant_temp, 1),
                    "battery_voltage": round(vehicle.battery_voltage, 2),
                    "diagnostic_code": None,
                }

                final_frame = apply_sensor_anomalies(telemetry_frame)

                f.write(json.dumps(final_frame) + "\n")
                total_written += 1

    print(f"[generator] Done! Written {total_written} records to: {RAW_DATA_PATH}")


if __name__ == "__main__":
    generate_telemetry_data()