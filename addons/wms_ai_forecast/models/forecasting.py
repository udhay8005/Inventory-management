"""Lightweight, offline forecasting.

Pure Python module with no Odoo imports — easy to unit-test and easy to move
to the optional `ai_worker` container if you want forecasts off the Odoo
process.

Approach:
  * Take a daily-bucketed time series of outflow (positive = consumption).
  * Resample to weekly to reduce noise.
  * Pick a model based on series length:
      - Naive (30-day average) for very short series (< 8 weekly obs)
      - SES                  for short/no seasonality (8..23 obs)
      - Holt-Winters add.    for >= 24 obs (capable of yearly weekly seasonality)
  * Forecast `horizon_days` ahead and report total + RMSE + model name.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

try:
    import numpy as np
    import pandas as pd
    from statsmodels.tsa.holtwinters import ExponentialSmoothing, SimpleExpSmoothing

    _HAS_STATSMODELS = True
except Exception:  # noqa: BLE001
    _HAS_STATSMODELS = False


@dataclass
class ForecastResult:
    predicted_qty: float  # total qty over horizon_days
    daily_avg: float
    monthly_avg: float
    model_name: str  # "HoltWinters" / "SES" / "Naive30"
    rmse: float  # 0 for Naive
    velocity_class: str  # fast / normal / slow / dead

    @property
    def is_zero(self) -> bool:
        return self.predicted_qty <= 0


def _classify(monthly_avg: float, has_recent_activity: bool) -> str:
    if not has_recent_activity:
        return "dead"
    if monthly_avg > 100:
        return "fast"
    if monthly_avg > 10:
        return "normal"
    return "slow"


def _to_weekly(observations: Iterable[tuple[datetime, float]]):
    """Rolls (date, qty) pairs into a weekly-frequency pandas Series.
    Missing weeks filled with 0.
    """
    if not _HAS_STATSMODELS:
        raise RuntimeError("statsmodels/pandas not installed")
    if not observations:
        return pd.Series(dtype="float64")

    df = pd.DataFrame(observations, columns=["date", "qty"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    weekly = df["qty"].resample("W").sum().fillna(0.0)
    return weekly


def forecast(
    observations: Iterable[tuple[datetime, float]], horizon_days: int = 30
) -> ForecastResult:
    """Return a ForecastResult for the given list of (date, outflow_qty)."""
    if not _HAS_STATSMODELS:
        # Graceful degradation: a 30-day average computed in pure Python.
        return _naive_fallback(observations, horizon_days)

    weekly = _to_weekly(observations)
    n = len(weekly)
    horizon_weeks = max(1, int(math.ceil(horizon_days / 7.0)))

    if n < 4:
        return _naive_fallback(observations, horizon_days)

    cutoff = max(1, int(n * 0.8))
    train = weekly.iloc[:cutoff]
    test = weekly.iloc[cutoff:]

    model_name = "SES"
    try:
        if n >= 24:
            model = ExponentialSmoothing(
                train,
                trend="add",
                seasonal="add",
                seasonal_periods=4,
                initialization_method="estimated",
            ).fit(optimized=True, use_brute=False)
            model_name = "HoltWinters"
        else:
            model = SimpleExpSmoothing(train, initialization_method="estimated").fit()
    except Exception:
        # SES is the safer fallback when HW fails (e.g. data too flat)
        model = SimpleExpSmoothing(train, initialization_method="estimated").fit()
        model_name = "SES"

    # Holdout RMSE
    rmse = 0.0
    if len(test) > 0:
        try:
            yhat = model.forecast(len(test))
            errs = np.array(test.values) - np.array(yhat.values)
            rmse = float(math.sqrt(np.mean(errs**2)))
        except Exception:
            rmse = 0.0

    forecast_series = model.forecast(horizon_weeks)
    forecast_total = float(max(0.0, np.sum(forecast_series.values)))

    daily_avg = forecast_total / horizon_days
    monthly_avg = daily_avg * 30.0
    # has_recent_activity = any qty in the last 12 weeks
    has_recent_activity = bool(weekly.tail(12).sum() > 0)
    cls = _classify(monthly_avg, has_recent_activity)

    return ForecastResult(
        predicted_qty=forecast_total,
        daily_avg=daily_avg,
        monthly_avg=monthly_avg,
        model_name=model_name,
        rmse=rmse,
        velocity_class=cls,
    )


def _naive_fallback(
    observations: Iterable[tuple[datetime, float]], horizon_days: int
) -> ForecastResult:
    obs = list(observations)
    if not obs:
        return ForecastResult(0.0, 0.0, 0.0, "Naive30", 0.0, "dead")
    cutoff = datetime.utcnow() - timedelta(days=30)
    recent = [q for d, q in obs if d >= cutoff]
    monthly_avg = sum(recent) if recent else 0.0
    daily_avg = monthly_avg / 30.0
    predicted = daily_avg * horizon_days
    has_recent = monthly_avg > 0
    cls = _classify(monthly_avg, has_recent)
    return ForecastResult(predicted, daily_avg, monthly_avg, "Naive30", 0.0, cls)


def reorder_recommendation(
    on_hand: float,
    on_order: float,
    daily_avg: float,
    lead_time_days: int,
    safety_stock: float,
    horizon_days: int,
) -> tuple[float, float | None]:
    """Returns (suggested_order_qty, reorder_date_or_None).

    Pure deterministic — no AI here. AI's job ended at producing daily_avg.
    """
    reorder_point = lead_time_days * daily_avg + safety_stock
    horizon_demand = daily_avg * horizon_days
    need = horizon_demand + safety_stock - on_hand - on_order
    suggested = max(0.0, need)

    reorder_date = None
    if daily_avg > 0:
        days_until_rop = max(0.0, (on_hand + on_order - reorder_point) / daily_avg)
        reorder_date = datetime.utcnow() + timedelta(days=days_until_rop)
    return suggested, reorder_date
