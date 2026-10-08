from datetime import datetime
from pathlib import Path
import sqlite3
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DATA_PATH = BASE_DIR / "data" / "raw" / "telemetry.jsonl"
PARQUET_PATH = BASE_DIR / "data" / "processed" / "telemetry_clean.parquet"
SQLITE_PATH = BASE_DIR / "data" / "processed" / "fleet_data.db"


def extract(source_path: Path) -> pd.DataFrame:
    """Read raw JSON lines into a DataFrame with parsed UTC timestamps."""
    if not source_path.exists():
        raise FileNotFoundError(f"Missing input file: {source_path}")

    df = pd.read_json(source_path, lines=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


def transform(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, int]:
    """Sanitize sensor readings, flag warnings, and calculate fleet aggregates."""
    initial_count = len(df)

    df_valid = df.dropna(subset=["speed_kmh", "coolant_temp_c", "battery_voltage"])
    valid_mask = (
        (df_valid["speed_kmh"] >= 0.0)
        & (df_valid["speed_kmh"] <= 200.0)
        & (df_valid["coolant_temp_c"] >= -20.0)
        & (df_valid["coolant_temp_c"] <= 130.0)
    )
    df_clean = df_valid[valid_mask].copy()
    dropped_count = initial_count - len(df_clean)

    # Feature engineering: operational warnings
    df_clean["is_overheating"] = df_clean["coolant_temp_c"] > 105.0
    df_clean["is_speeding"] = df_clean["speed_kmh"] > 130.0
    df_clean["low_battery"] = df_clean["battery_voltage"] < 11.8

    # Aggregated fleet summary
    fleet_summary = (
        df_clean.groupby("vehicle_id")
        .agg(
            avg_speed_kmh=("speed_kmh", "mean"),
            max_speed_kmh=("speed_kmh", "max"),
            avg_coolant_temp_c=("coolant_temp_c", "mean"),
            max_coolant_temp_c=("coolant_temp_c", "max"),
            total_overheat_alerts=("is_overheating", "sum"),
            total_speeding_alerts=("is_speeding", "sum"),
            total_records=("event_id", "count"),
        )
        .reset_index()
    )

    fleet_summary["avg_speed_kmh"] = fleet_summary["avg_speed_kmh"].round(1)
    fleet_summary["avg_coolant_temp_c"] = fleet_summary["avg_coolant_temp_c"].round(1)

    # Isolated alerts view
    alerts_mask = (
        df_clean["diagnostic_code"].notna()
        | df_clean["is_overheating"]
        | df_clean["low_battery"]
    )
    alerts_df = df_clean[alerts_mask].copy()

    return df_clean, fleet_summary, alerts_df, dropped_count


def load(df_clean: pd.DataFrame, fleet_summary: pd.DataFrame, alerts_df: pd.DataFrame) -> None:
    """Save processed datasets to dual storage (Parquet and SQLite)."""
    PARQUET_PATH.parent.mkdir(parents=True, exist_ok=True)

    df_clean.to_parquet(PARQUET_PATH, engine="pyarrow", index=False)

    with sqlite3.connect(str(SQLITE_PATH)) as conn:
        fleet_summary.to_sql("fleet_summary", conn, if_exists="replace", index=False)
        alerts_df.to_sql("diagnostic_alerts", conn, if_exists="replace", index=False)


def run_pipeline() -> None:
    """Orchestrate the end-to-end ingestion and persistence flow."""
    start_time = datetime.now()
    print(f"[etl] extracting from {RAW_DATA_PATH}")
    raw_df = extract(RAW_DATA_PATH)

    clean_df, summary_df, alerts_df, dropped = transform(raw_df)
    print(f"[etl] data quality check: dropped {dropped} invalid rows ({len(clean_df)} valid)")

    load(clean_df, summary_df, alerts_df)
    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"[etl] pipeline completed in {elapsed:.2f}s")


if __name__ == "__main__":
    run_pipeline()