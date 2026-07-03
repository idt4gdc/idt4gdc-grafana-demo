import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import psycopg2

import torch

from darts import TimeSeries
from darts.dataprocessing.transformers import Scaler
from darts.models import TFTModel
from darts.utils.timeseries_generation import datetime_attribute_timeseries

# PyTorch 2.6 changed weights_only default to True, which breaks checkpoints that
# contain darts likelihood globals. Patch it back for trusted internal checkpoints.
_orig_torch_load = torch.load
def _torch_load_compat(*args, **kwargs):
    kwargs["weights_only"] = False
    return _orig_torch_load(*args, **kwargs)
torch.load = _torch_load_compat

from psycopg2.extras import execute_values

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://grafana:grafana@localhost:5432/opsdemo")

SS_IDS = [int(x.strip()) for x in os.getenv("SS_IDS", os.getenv("SS_ID", "10006")).split(",")]
BACKFILL_DAYS = int(os.getenv("BACKFILL_DAYS", "7"))
RUN_HOUR = int(os.getenv("RUN_HOUR", "0"))

DATA_ROOT = Path(os.getenv("DATA_ROOT", "/forecast-data"))
MODEL_PATH = DATA_ROOT / "models" / "forecast_global.pt"
META_PATH = DATA_ROOT / "metadata.csv"
DATA_DIR = DATA_ROOT / "data"
SCALERS_DIR = DATA_ROOT / "scalers" / "covariates"

COVARIATES = [
    "cloud_cover",
    "shortwave_radiation",
    "direct_radiation",
    "diffuse_radiation",
    "temperature_2m",
    "relative_humidity_2m",
    "dew_point_2m",
    "surface_pressure",
    "wind_speed_10m",
]

INPUT_LEN = 24 * 2     # 48 half-hour steps = 24 h lookback
FORECAST_LEN = 24 * 2  # 48 half-hour steps = 24 h ahead


def wait_for_db(url: str) -> psycopg2.extensions.connection:
    while True:
        try:
            conn = psycopg2.connect(url)
            log.info("Database connected")
            return conn
        except psycopg2.OperationalError:
            log.info("Waiting for database...")
            time.sleep(3)


def load_panel_data(ss_id: int) -> tuple:
    meta = pd.read_csv(META_PATH)
    panel = meta[meta["ss_id"] == ss_id].iloc[0]

    df = pd.read_parquet(DATA_DIR / str(ss_id) / "all.parquet")
    assert isinstance(df.index, pd.DatetimeIndex)
    df.index = df.index.tz_convert(None)  # strip UTC tz to naive for darts compatibility

    if df.index.duplicated().any():
        n_dupes = int(df.index.duplicated().sum())
        log.warning(f"Panel {ss_id}: dropping {n_dupes} rows with duplicate timestamps (source data overlap)")
        df = df[~df.index.duplicated(keep="first")]

    off_grid = (df.index.minute % 30 != 0) | (df.index.second != 0)
    if off_grid.any():
        n_off_grid = int(off_grid.sum())
        log.warning(f"Panel {ss_id}: dropping {n_off_grid} rows not aligned to the 30-minute grid")
        df = df[~off_grid]

    df["normalised"] = df["generation_Wh"] / (panel.kWp * 1000)

    return panel, df


def build_series(df: pd.DataFrame, panel) -> tuple:
    static_cov = pd.DataFrame(
        {"lat": [panel.latitude_rounded], "lon": [panel.longitude_rounded], "kwp": [panel.kWp]},
        dtype=np.float32,
    )

    series = TimeSeries.from_dataframe(df, value_cols="normalised", fillna_value=0, freq="30min")
    scaler = Scaler()
    series_scaled = scaler.fit_transform(series)
    series_scaled = series_scaled.with_static_covariates(static_cov)

    covariates = None
    for param in COVARIATES:
        covariate = TimeSeries.from_series(df[param].astype(np.float32), freq="30min", fillna_value=0)
        covariate_scaler = joblib.load(SCALERS_DIR / f"global_{param}.pkl")
        covariate_scaled = covariate_scaler.transform(covariate)
        covariates = covariates.stack(covariate_scaled) if covariates is not None else covariate_scaled

    month_series = datetime_attribute_timeseries(series, "month", one_hot=True).astype(np.float32)
    hour_series = datetime_attribute_timeseries(series, "hour", one_hot=True).astype(np.float32)
    covariates = covariates.stack(month_series).stack(hour_series)

    return series_scaled, scaler, covariates


def run_forecast(model, series_scaled, scaler, covariates, panel, forecast_date: pd.Timestamp) -> tuple:
    start = forecast_date - pd.Timedelta(days=1)
    end = forecast_date + pd.Timedelta(days=1)

    pred_input = series_scaled.slice(start, forecast_date)
    future_covariates = covariates.slice(start, end)

    prediction = model.predict(
        n=FORECAST_LEN,
        series=pred_input,
        future_covariates=future_covariates,
        verbose=False,
    )
    prediction = scaler.inverse_transform(prediction) * (panel.kWp * 1000)

    # Actuals may not exist for the most recent forecast date (today)
    actual_slice = series_scaled.slice(forecast_date, end)
    actual = scaler.inverse_transform(actual_slice) * (panel.kWp * 1000) if len(actual_slice) > 0 else None

    return prediction, actual


def build_rows(prediction, actual, df: pd.DataFrame, ss_id: int, time_offset: pd.Timedelta) -> list:
    pred_df = prediction.to_dataframe()
    actual_df = actual.to_dataframe() if actual is not None else pd.DataFrame()

    rows = []
    for ts in pred_df.index:
        shifted_ts = (ts + time_offset).to_pydatetime().replace(tzinfo=timezone.utc)
        forecast_wh = round(float(pred_df.loc[ts].iloc[0]), 2)
        actual_wh = round(float(actual_df.loc[ts].iloc[0]), 2) if ts in actual_df.index else None
        cloud_cover = float(df.at[ts, "cloud_cover"]) if ts in df.index else None
        shortwave = float(df.at[ts, "shortwave_radiation"]) if ts in df.index else None
        rows.append((shifted_ts, ss_id, forecast_wh, actual_wh, cloud_cover, shortwave))

    return rows


def upsert_rows(conn, rows: list) -> None:
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO forecast_generation (ts, ss_id, forecast_wh, actual_wh, cloud_cover, shortwave_radiation)
            VALUES %s
            ON CONFLICT (ts, ss_id) DO UPDATE SET
                forecast_wh         = EXCLUDED.forecast_wh,
                actual_wh           = EXCLUDED.actual_wh,
                cloud_cover         = EXCLUDED.cloud_cover,
                shortwave_radiation = EXCLUDED.shortwave_radiation
            """,
            rows,
        )
    conn.commit()
    log.info(f"Upserted {len(rows)} forecast rows")


def seconds_until(run_hour: int) -> float:
    now = datetime.now(timezone.utc)
    next_run = now.replace(hour=run_hour, minute=0, second=0, microsecond=0)
    if next_run <= now:
        next_run += timedelta(days=1)
    return (next_run - now).total_seconds()


def prepare_panel(ss_id: int) -> tuple:
    panel, df = load_panel_data(ss_id)
    data_max = df.index.max().normalize()

    # Extend covariates by one day so the model can forecast data_max itself
    # (it requires future covariates through data_max + 1 day).
    extra_index = pd.date_range(df.index[-1] + pd.Timedelta("30min"), periods=FORECAST_LEN, freq="30min")
    extra = df.iloc[-FORECAST_LEN:].copy()
    extra.index = extra_index
    extra[["generation_Wh", "normalised"]] = np.float32(0.0)
    df = pd.concat([df, extra])
    float_cols = df.select_dtypes(include=["float64"]).columns
    df[float_cols] = df[float_cols].astype(np.float32)

    series_scaled, scaler, covariates = build_series(df, panel)
    two_years_ago = pd.Timestamp(datetime.now(timezone.utc).date()) - pd.DateOffset(years=2) + pd.Timedelta(days=1)
    time_offset = two_years_ago - data_max
    log.info(f"Panel {ss_id}: data ends {data_max.date()}, anchoring to {two_years_ago.date()} (offset {time_offset.days} days)")

    return panel, df, series_scaled, scaler, covariates, data_max, time_offset


def backfill_panel(conn, model, ss_id: int, panel, df, series_scaled, scaler, covariates, data_max, time_offset) -> None:
    log.info(f"Panel {ss_id}: backfilling {BACKFILL_DAYS} days...")
    for day in range(BACKFILL_DAYS, -1, -1):
        forecast_date = data_max - pd.Timedelta(days=day)
        input_start = forecast_date - pd.Timedelta(days=1)

        if input_start < df.index.min():
            log.debug(f"Panel {ss_id}: skipping {forecast_date.date()}: insufficient input history")
            continue

        try:
            prediction, actual = run_forecast(model, series_scaled, scaler, covariates, panel, forecast_date)
            if forecast_date >= data_max:
                actual = None  # extended zero-pad rows are not real actuals
            rows = build_rows(prediction, actual, df, ss_id, time_offset)
            upsert_rows(conn, rows)
            shifted = (forecast_date + time_offset).date()
            log.info(f"Panel {ss_id}: backfilled {forecast_date.date()} → stored as {shifted}")
        except Exception:
            log.exception(f"Panel {ss_id}: backfill failed for {forecast_date.date()}")


def main():
    conn = wait_for_db(DATABASE_URL)

    log.info("Loading model...")
    model = TFTModel.load(
        str(MODEL_PATH),
        map_location="cpu",
        pl_trainer_kwargs={"accelerator": "cpu"},
    )

    log.info(f"Preparing {len(SS_IDS)} panel(s): {SS_IDS}")
    panels = []
    for ss_id in SS_IDS:
        try:
            panels.append((ss_id, *prepare_panel(ss_id)))
        except Exception:
            log.exception(f"Panel {ss_id}: failed to prepare, skipping")

    for ss_id, panel, df, series_scaled, scaler, covariates, data_max, time_offset in panels:
        backfill_panel(conn, model, ss_id, panel, df, series_scaled, scaler, covariates, data_max, time_offset)

    while True:
        sleep_s = seconds_until(RUN_HOUR)
        log.info(f"Next daily forecast in {sleep_s / 3600:.1f} h")
        time.sleep(sleep_s)

        today = pd.Timestamp(datetime.now(timezone.utc).date())
        for ss_id, panel, df, series_scaled, scaler, covariates, data_max, time_offset in panels:
            source_date = today - time_offset

            if source_date < df.index.min() + pd.Timedelta(days=1) or source_date > data_max:
                log.warning(f"Panel {ss_id}: source date {source_date.date()} outside data range, skipping")
                continue

            try:
                prediction, actual = run_forecast(model, series_scaled, scaler, covariates, panel, source_date)
                rows = build_rows(prediction, actual, df, ss_id, time_offset)
                upsert_rows(conn, rows)
                log.info(f"Panel {ss_id}: daily forecast complete for {today.date()}")
            except Exception:
                log.exception(f"Panel {ss_id}: daily forecast failed")


if __name__ == "__main__":
    main()