import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Setare căi absolute ancorate la rădăcina proiectului
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DATA_PATH = BASE_DIR / "data" / "raw" / "telemetry.jsonl"

VEHICLES = [f"VEHICLE_{i:02d}" for i in range(1, 6)]  # VEHICLE_01 .. VEHICLE_05
DTC_CODES = ["P0217", "P0117", "P0300", None]  # Coduri OBD-II reale vs starea normală (None)


def generate_telemetry_data(num_records_per_vehicle: int = 2000) -> None:
    """Generează un set de date sintetice de telemetrie auto în format JSON Lines (JSONL)."""
    # Asigură existența folderului data/raw/
    RAW_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)

    start_time = datetime.now(timezone.utc) - timedelta(days=1)
    records_written = 0

    with open(RAW_DATA_PATH, "w", encoding="utf-8") as f:
        for vehicle_id in VEHICLES:
            current_time = start_time
            # Stări inițiale pentru fizica motorului
            coolant_temp = random.uniform(20.0, 40.0)
            speed = 0.0

            for i in range(num_records_per_vehicle):
                current_time += timedelta(seconds=5)  # Eșantionare la fiecare 5 secunde

                # 1. Simulare dinamică viteza și RPM
                speed_change = random.uniform(-5.0, 5.0)
                speed = max(0.0, min(160.0, speed + speed_change))
                rpm = int(speed * 30 + random.uniform(800, 1200)) if speed > 0 else random.randint(750, 850)

                # 2. Inerție termică (temperatura motorului crește în mers)
                if speed > 0 and coolant_temp < 90.0:
                    coolant_temp += random.uniform(0.1, 0.4)
                elif speed == 0 and coolant_temp > 30.0:
                    coolant_temp -= random.uniform(0.1, 0.2)

                # 3. Tensiune baterie / alternator
                battery_voltage = random.uniform(13.6, 14.4)

                # --- Injectare anomali deliberate pentru testarea filtrelor ETL ---

                # Zgomot de senzor / anomalii fizice (1% șansă)
                if random.random() < 0.01:
                    speed = random.choice([-10.0, 250.0])  # Viteze imposibile
                if random.random() < 0.01:
                    coolant_temp = random.choice([-50.0, 150.0])  # Temperaturi extreme
                if random.random() < 0.01:
                    battery_voltage = random.uniform(9.0, 11.5)  # Baterie descărcată

                # Căderi de semnal hardware / dropout de senzor (1% șansă de valori None)
                speed_val = None if random.random() < 0.01 else round(speed, 1)
                temp_val = None if random.random() < 0.01 else round(coolant_temp, 1)
                volt_val = None if random.random() < 0.01 else round(battery_voltage, 2)

                # Coduri de eroare de diagnosticare OBD-II (1.5% șansă)
                dtc_code = random.choice(DTC_CODES) if random.random() < 0.015 else None

                # În caz de cod P0217, simulăm supraîncălzire reală
                if dtc_code == "P0217" and temp_val is not None:
                    temp_val = round(random.uniform(108.0, 120.0), 1)

                record = {
                    "event_id": f"{vehicle_id}_{i:05d}",
                    "vehicle_id": vehicle_id,
                    "timestamp": current_time.isoformat(),
                    "speed_kmh": speed_val,
                    "engine_rpm": rpm,
                    "coolant_temp_c": temp_val,
                    "battery_voltage": volt_val,
                    "diagnostic_code": dtc_code,
                }

                f.write(json.dumps(record) + "\n")
                records_written += 1

    print(f"[generator] A generat {records_written} pachete de telemetrie în: {RAW_DATA_PATH}")


if __name__ == "__main__":
    generate_telemetry_data()