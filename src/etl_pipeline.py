from datetime import datetime
import os
from pathlib import Path
import sqlite3
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DATA_PATH = BASE_DIR / "data" / "raw" / "telemetry.jsonl"
PARQUET_OUTPUT_PATH = BASE_DIR / "data" / "processed" / "telemetry_clean.parquet"
SQLITE_DB_PATH = BASE_DIR / "data" / "processed" / "fleet_data.db"


def extract(file_path: Path | str) -> pd.DataFrame:
    """Description:
        Ingests newline-delimited raw JSON telemetry logs into a DataFrame
        and casts timestamps to UTC datetimes.
    Pre:
        file_path exists and points to a valid JSON Lines telemetry file.
    Post:
        Returns a DataFrame with a parsed 'timestamp' column in UTC format.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(
            f"Input file not found at '{file_path}'. Run generate_data.py first."
        )

    df = pd.read_json(file_path, lines=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


def transform(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, int]:
    """Description:
        Sanitizes raw telemetry via physical boundary masking, engineers alert flags,
        and aggregates high-level fleet operational metrics.
    Pre:
        df contains sensor metrics: 'speed_kmh', 'coolant_temp_c', 'battery_voltage',
        'vehicle_id', and 'event_id'.
    Post:
        Returns a 4-tuple containing (df_clean, fleet_summary, alerts_df, dropped_count).
    """
    initial_count = len(df)

    df_valid = df.dropna(
        subset=["speed_kmh", "coolant_temp_c", "battery_voltage"]
    )
    valid_mask = (
        (df_valid["speed_kmh"] >= 0.0)
        & (df_valid["speed_kmh"] <= 200.0)
        & (df_valid["coolant_temp_c"] >= -20.0)
        & (df_valid["coolant_temp_c"] <= 130.0)
    )
    df_clean = df_valid[valid_mask].copy()
    dropped_count = initial_count - len(df_clean)

    df_clean["is_overheating"] = df_clean["coolant_temp_c"] > 105.0
    df_clean["is_speeding"] = df_clean["speed_kmh"] > 130.0
    df_clean["low_battery"] = df_clean["battery_voltage"] < 11.8

    fleet_summary = (
        df_clean.groupby("vehicle_id")
        .agg(
            avg_speed_kmh=("speed_kmh", "mean"),
            max_speed_kmh=("speed_kmh", "max"),
            avg_coolant_temp_c=("coolant_temp_c", "mean"),
            max_coolant_temp_c=("coolant_temp_c", "max"),
            total_overheat_alerts=("is_overheating", "sum"),
            total_speeding_alerts=("is_speeding", "sum"),
            total_records_processed=("event_id", "count"),
        )
        .reset_index()
    )

    fleet_summary["avg_speed_kmh"] = fleet_summary["avg_speed_kmh"].round(1)
    fleet_summary["avg_coolant_temp_c"] = fleet_summary[
        "avg_coolant_temp_c"
    ].round(1)

    alerts_mask = (
        df_clean["diagnostic_code"].notna()
        | df_clean["is_overheating"]
        | df_clean["low_battery"]
    )
    alerts_df = df_clean[alerts_mask].copy()

    return df_clean, fleet_summary, alerts_df, dropped_count


def load(
    df_clean: pd.DataFrame, fleet_summary: pd.DataFrame, alerts_df: pd.DataFrame
) -> None:
    """Description:
        Persists clean telemetry to compressed columnar Parquet and aggregates
        to relational SQLite tables under a dual-storage design.
    Pre:
        Parent output directories are writable; inputs are valid pandas DataFrames.
    Post:
        Creates or replaces PARQUET_OUTPUT_PATH and SQLITE_DB_PATH tables
        'fleet_summary' and 'diagnostic_alerts'.
    """
    os.makedirs(PARQUET_OUTPUT_PATH.parent, exist_ok=True)

    df_clean.to_parquet(PARQUET_OUTPUT_PATH, engine="pyarrow", index=False)

    with sqlite3.connect(str(SQLITE_DB_PATH)) as conn:
        fleet_summary.to_sql(
            "fleet_summary", conn, if_exists="replace", index=False
        )
        alerts_df.to_sql(
            "diagnostic_alerts", conn, if_exists="replace", index=False
        )


def run_pipeline() -> None:
    """Description:
        Coordinates end-to-end execution of the telemetry ETL flow and logs
        pipeline health metrics.
    Pre:
        RAW_DATA_PATH points to available simulated input data.
    Post:
        Completes extraction, data quality sanitization, and dual-layer persistence.
    """
    print("[ETL] Starting pipeline execution...")
    start_time = datetime.now()

    print(f"[ETL] Extracting records from '{RAW_DATA_PATH}'...")
    raw_df = extract(RAW_DATA_PATH)
    print(f"[ETL] Successfully loaded {len(raw_df)} raw records.")

    print("[ETL] Performing data cleaning, filtering, and aggregation...")
    clean_df, summary_df, alerts_df, dropped_count = transform(raw_df)
    print(
        f"[ETL] Data quality check: Dropped {dropped_count} corrupted/anomalous rows."
    )
    print(f"[ETL] Retained {len(clean_df)} clean telemetry events.")
    print(f"[ETL] Identified {len(alerts_df)} diagnostic alerts and warnings.")

    print("[ETL] Loading clean data to Parquet and SQLite storage...")
    load(clean_df, summary_df, alerts_df)

    elapsed_time = (datetime.now() - start_time).total_seconds()
    print(f"[ETL] Pipeline finished successfully in {elapsed_time:.2f} seconds.")
    print(f"      - Analytical Store: '{PARQUET_OUTPUT_PATH}'")
    print(f"      - Operational Store: '{SQLITE_DB_PATH}'")


if __name__ == "__main__":
    run_pipeline()