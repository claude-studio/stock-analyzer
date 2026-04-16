"""기술적 지표 계산 모듈.

pandas-ta가 설치되어 있으면 사용하고, 없으면 pandas 직접 구현으로 대체한다.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import structlog

logger = structlog.get_logger(__name__)

try:
    import pandas_ta  # type: ignore[import-untyped]

    _HAS_PANDAS_TA = True
    logger.debug("pandas_ta 사용 가능")
except ImportError:
    _HAS_PANDAS_TA = False
    logger.debug("pandas_ta 미설치 -- pandas 직접 구현 사용")


def _calculate_sma(series: pd.Series, window: int) -> pd.Series:
    """단순이동평균(SMA)."""
    return series.rolling(window=window).mean()


def _calculate_ema(series: pd.Series, span: int) -> pd.Series:
    """지수이동평균(EMA)."""
    return series.ewm(span=span, adjust=False).mean()


def _calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """RSI (Relative Strength Index)."""
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(window=period).mean()
    loss = (-delta.clip(upper=0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - 100 / (1 + rs)


def _calculate_macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD, Signal, Histogram."""
    ema_fast = _calculate_ema(series, fast)
    ema_slow = _calculate_ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def _calculate_bollinger_bands(
    series: pd.Series,
    window: int = 20,
    num_std: float = 2.0,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """볼린저밴드 (upper, middle, lower)."""
    middle = _calculate_sma(series, window)
    std = series.rolling(window=window).std()
    upper = middle + num_std * std
    lower = middle - num_std * std
    return upper, middle, lower


def _calculate_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """ATR (Average True Range)."""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


def _determine_price_position(close_last: float, sma20_last: float | None) -> str:
    """현재가와 SMA20의 상대 위치를 판단한다."""
    if sma20_last is None:
        return "at_ma20"
    tolerance = sma20_last * 0.005
    if close_last > sma20_last + tolerance:
        return "above_ma20"
    if close_last < sma20_last - tolerance:
        return "below_ma20"
    return "at_ma20"


def _determine_trend(sma20: pd.Series, lookback: int = 5) -> str:
    """SMA20 기울기 기반 추세 판단.

    최근 lookback일간 SMA20의 변화율로 추세를 판단한다.
    """
    recent = sma20.dropna().tail(lookback)
    if len(recent) < 2:
        return "sideways"

    slope = (recent.iloc[-1] - recent.iloc[0]) / recent.iloc[0]
    threshold = 0.01

    if slope > threshold:
        return "uptrend"
    if slope < -threshold:
        return "downtrend"
    return "sideways"


def _safe_scalar(value: Any) -> float | None:
    """pandas/numpy 값을 Python float 또는 None으로 변환한다."""
    if pd.isna(value):
        return None
    return float(value)


def _calculate_with_pandas(df: pd.DataFrame) -> dict[str, float | str | None]:
    """pandas 직접 구현으로 기술적 지표를 계산한다."""
    close = df["close"]
    high = df["high"]
    low = df["low"]

    # SMA
    sma_5 = _calculate_sma(close, 5)
    sma_20 = _calculate_sma(close, 20)
    sma_60 = _calculate_sma(close, 60)
    sma_120 = _calculate_sma(close, 120)

    # EMA
    ema_12 = _calculate_ema(close, 12)
    ema_26 = _calculate_ema(close, 26)

    # RSI
    rsi_14 = _calculate_rsi(close, 14)

    # MACD
    macd_line, macd_signal, macd_hist = _calculate_macd(close)

    # Bollinger Bands
    bb_upper, bb_middle, bb_lower = _calculate_bollinger_bands(close)

    # ATR
    atr_14 = _calculate_atr(high, low, close, 14)

    # 추세/위치 판단
    sma20_last = _safe_scalar(sma_20.iloc[-1])
    close_last = float(close.iloc[-1])
    price_position = _determine_price_position(close_last, sma20_last)
    trend = _determine_trend(sma_20)

    return {
        "sma_5": _safe_scalar(sma_5.iloc[-1]),
        "sma_20": _safe_scalar(sma_20.iloc[-1]),
        "sma_60": _safe_scalar(sma_60.iloc[-1]),
        "sma_120": _safe_scalar(sma_120.iloc[-1]),
        "ema_12": _safe_scalar(ema_12.iloc[-1]),
        "ema_26": _safe_scalar(ema_26.iloc[-1]),
        "rsi_14": _safe_scalar(rsi_14.iloc[-1]),
        "macd": _safe_scalar(macd_line.iloc[-1]),
        "macd_signal": _safe_scalar(macd_signal.iloc[-1]),
        "macd_hist": _safe_scalar(macd_hist.iloc[-1]),
        "bb_upper": _safe_scalar(bb_upper.iloc[-1]),
        "bb_middle": _safe_scalar(bb_middle.iloc[-1]),
        "bb_lower": _safe_scalar(bb_lower.iloc[-1]),
        "atr_14": _safe_scalar(atr_14.iloc[-1]),
        "price_position": price_position,
        "trend": trend,
    }


def _calculate_with_pandas_ta(df: pd.DataFrame) -> dict[str, float | str | None]:
    """pandas-ta로 기술적 지표를 계산한다."""
    close = df["close"]
    high = df["high"]
    low = df["low"]

    # SMA
    sma_5 = pandas_ta.sma(close, length=5)
    sma_20 = pandas_ta.sma(close, length=20)
    sma_60 = pandas_ta.sma(close, length=60)
    sma_120 = pandas_ta.sma(close, length=120)

    # EMA
    ema_12 = pandas_ta.ema(close, length=12)
    ema_26 = pandas_ta.ema(close, length=26)

    # RSI
    rsi_14 = pandas_ta.rsi(close, length=14)

    # MACD
    macd_result = pandas_ta.macd(close, fast=12, slow=26, signal=9)
    macd_line = macd_result.iloc[:, 0]
    macd_signal = macd_result.iloc[:, 1]
    macd_hist = macd_result.iloc[:, 2]

    # Bollinger Bands
    bb_result = pandas_ta.bbands(close, length=20, std=2.0)
    bb_lower = bb_result.iloc[:, 0]
    bb_middle = bb_result.iloc[:, 1]
    bb_upper = bb_result.iloc[:, 2]

    # ATR
    atr_14 = pandas_ta.atr(high, low, close, length=14)

    # 추세/위치 판단
    sma20_last = _safe_scalar(sma_20.iloc[-1])
    close_last = float(close.iloc[-1])
    price_position = _determine_price_position(close_last, sma20_last)
    trend = _determine_trend(sma_20)

    return {
        "sma_5": _safe_scalar(sma_5.iloc[-1]),
        "sma_20": _safe_scalar(sma_20.iloc[-1]),
        "sma_60": _safe_scalar(sma_60.iloc[-1]),
        "sma_120": _safe_scalar(sma_120.iloc[-1]),
        "ema_12": _safe_scalar(ema_12.iloc[-1]),
        "ema_26": _safe_scalar(ema_26.iloc[-1]),
        "rsi_14": _safe_scalar(rsi_14.iloc[-1]),
        "macd": _safe_scalar(macd_line.iloc[-1]),
        "macd_signal": _safe_scalar(macd_signal.iloc[-1]),
        "macd_hist": _safe_scalar(macd_hist.iloc[-1]),
        "bb_upper": _safe_scalar(bb_upper.iloc[-1]),
        "bb_middle": _safe_scalar(bb_middle.iloc[-1]),
        "bb_lower": _safe_scalar(bb_lower.iloc[-1]),
        "atr_14": _safe_scalar(atr_14.iloc[-1]),
        "price_position": price_position,
        "trend": trend,
    }


def calculate_technical_indicators(df: pd.DataFrame) -> dict[str, float | str | None]:
    """기술적 지표를 계산하여 dict로 반환한다.

    입력 DataFrame 필수 컬럼: open, high, low, close, volume (소문자, float).
    마지막 행 기준 값을 반환하며, NaN은 None으로 변환된다.

    Args:
        df: OHLCV 가격 데이터 DataFrame

    Returns:
        기술적 지표 dict (SMA, EMA, RSI, MACD, BB, ATR, 추세 등)

    Raises:
        ValueError: 필수 컬럼이 누락된 경우
    """
    required_columns = {"open", "high", "low", "close", "volume"}
    missing = required_columns - set(df.columns)
    if missing:
        raise ValueError(f"필수 컬럼 누락: {missing}")

    if len(df) < 2:
        raise ValueError(f"최소 2행 이상의 데이터가 필요합니다 (현재: {len(df)}행)")

    if _HAS_PANDAS_TA:
        logger.info("pandas_ta로 기술적 지표 계산", rows=len(df))
        return _calculate_with_pandas_ta(df)

    logger.info("pandas 직접 구현으로 기술적 지표 계산", rows=len(df))
    return _calculate_with_pandas(df)
