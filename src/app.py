from pathlib import Path
import sqlite3
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Fleet Telemetry Monitor",
    page_icon="🚗",
    layout="wide",
)

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "fleet_data.db"
PARQUET_PATH = BASE_DIR / "data" / "processed" / "telemetry_clean.parquet"


@st.cache_data
def load_operational_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch fleet metrics and recent alert events from SQLite."""
    if not DB_PATH.exists():
        st.error(f"Database not found at `{DB_PATH}`. Run `python src/etl_pipeline.py` first.")
        st.stop()

    with sqlite3.connect(str(DB_PATH)) as conn:
        summary_df = pd.read_sql_query("SELECT * FROM fleet_summary", conn)
        alerts_df = pd.read_sql_query(
            "SELECT * FROM diagnostic_alerts ORDER BY timestamp DESC LIMIT 100",
            conn,
        )
    return summary_df, alerts_df


@st.cache_data
def load_timeseries_data() -> pd.DataFrame:
    """Load analytical metrics from the columnar Parquet store."""
    if not PARQUET_PATH.exists():
        st.error(f"Parquet file not found at `{PARQUET_PATH}`.")
        st.stop()

    return pd.read_parquet(
        str(PARQUET_PATH),
        columns=[
            "timestamp",
            "vehicle_id",
            "speed_kmh",
            "coolant_temp_c",
            "battery_voltage",
        ],
    )


st.title("🚗 Vehicle-to-Cloud Telemetry & Fleet Analytics")
st.caption("Fleet monitoring, operational health metrics, and OBD-II diagnostics.")

summary_df, alerts_df = load_operational_data()
timeseries_df = load_timeseries_data()

# Fleet KPI Cards
col1, col2, col3, col4 = st.columns(4)
col1.metric("Active Fleet", f"{len(summary_df)} vehicles")
col2.metric("Fleet Avg Speed", f"{summary_df['avg_speed_kmh'].mean():.1f} km/h")
col3.metric("Thermal Warnings", f"{summary_df['total_overheat_alerts'].sum()}", delta_color="inverse")
col4.metric("Logged Alerts", f"{len(alerts_df)}")

st.divider()

# Vehicle Inspection
st.subheader("Vehicle Inspection")
selected_vehicle = st.selectbox(
    "Vehicle ID",
    options=summary_df["vehicle_id"].unique(),
)

vehicle_data = timeseries_df[timeseries_df["vehicle_id"] == selected_vehicle].sort_values("timestamp")

col_left, col_right = st.columns(2)
with col_left:
    st.write("**Speed Profile (km/h)**")
    st.line_chart(vehicle_data.set_index("timestamp")["speed_kmh"])

with col_right:
    st.write("**Coolant Temperature (°C)**")
    st.line_chart(vehicle_data.set_index("timestamp")["coolant_temp_c"])

st.divider()

# Diagnostics Table
st.subheader("Diagnostic Events (OBD-II & Sensor Warnings)")
st.dataframe(
    alerts_df[
        [
            "timestamp",
            "vehicle_id",
            "diagnostic_code",
            "speed_kmh",
            "coolant_temp_c",
            "battery_voltage",
        ]
    ],
    use_container_width=True,
    hide_index=True,
)