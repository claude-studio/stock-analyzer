"""투자 분석 프롬프트 템플릿.

FinGPT HG-NC 4단계 구조화 프롬프트 기반.
"""

from __future__ import annotations

SYSTEM_PROMPT: str = """\
당신은 한국/미국 주식 시장 전문 투자 분석가입니다.
제공된 정량 데이터(기술적 지표, 수급, 가격 추이)를 기반으로 먼저 정량적 판단을 수행하고, \
그 위에 정성적 뉴스 분석을 결합하세요.

반드시 아래 JSON 구조로만 응답하세요. 다른 텍스트는 포함하지 마세요.

{
  "summary": "종합 분석 요약 (2-3문장)",
  "recommendation": "strong_buy | buy | hold | sell | strong_sell",
  "confidence": 0.0-1.0 사이의 확신도,
  "target_price": 목표가 (숫자),
  "bull_case": "먼저 Bull case(상승 시나리오)를 독립적으로 작성한 뒤, 반대 입장에서 Bear case(하락 시나리오)를 작성하세요. 두 관점을 균형 있게 고려한 후 최종 recommendation을 결정하세요. bull_case는 최소 2문장 이상 구체적으로 작성.",
  "bear_case": "Bear case(하락 시나리오)도 최소 2문장 이상 구체적으로 작성. bull_case와 독립적으로, 반대 관점에서 리스크와 하락 요인을 분석하세요.",
  "key_factors": ["핵심 요인 1", "핵심 요인 2", ...]
}

분석 순서:
1. 먼저 상승 시나리오(bull_case)를 독립적으로 충분히 분석하세요.
2. 그 다음, 완전히 반대 입장에서 하락 시나리오(bear_case)를 작성하세요.
3. 두 시나리오를 균형 있게 비교한 후 최종 recommendation과 confidence를 결정하세요.

모든 응답은 한국어로 작성하세요.
"""


def build_analysis_prompt(
    ticker: str,
    name: str,
    prices_summary: str,
    news_summary: str,
    market_context: str,
    technical_summary: str = "",
    fundamental_summary: str = "",
) -> str:
    """종목 분석용 프롬프트를 조합한다 (FinGPT HG-NC 4단계 구조).

    Args:
        ticker: 종목 코드
        name: 종목명
        prices_summary: 최근 거래일 일별 종가, 변동률, 거래량
        news_summary: 최근 뉴스 헤드라인 + 감성 키워드
        market_context: KOSPI/KOSDAQ 현재 수준
        technical_summary: 기술적 지표 요약 텍스트 (RSI, MACD, BB, SMA, 추세 등)
        fundamental_summary: 펀더멘탈 요약 텍스트
    """
    sections: list[str] = [SYSTEM_PROMPT]

    # 1단계: 기업 개요
    sections.append(f"""
## 기업 개요
- 종목코드: {ticker}
- 종목명: {name}""")

    # 2단계: 가격 데이터
    sections.append(f"""
## 가격 데이터 (최근 거래일)
{prices_summary}""")

    # 3단계: 기술적 지표
    if technical_summary:
        sections.append(f"""
## 기술적 지표
{technical_summary}""")

    # 펀더멘탈 (있으면 추가)
    if fundamental_summary:
        sections.append(f"""
## 펀더멘탈 분석
{fundamental_summary}""")

    # 4단계: 뉴스 및 시장 감성
    sections.append(f"""
## 뉴스 및 시장 감성
{news_summary}""")

    # 시장 컨텍스트
    sections.append(f"""
## 시장 컨텍스트
{market_context}""")

    sections.append("""
위 정량/정성 데이터를 종합하여 투자 분석 결과를 JSON으로 응답하세요.""")

    return "\n".join(sections)


def build_analysis_prompt_with_indicators(
    ticker: str,
    name: str,
    prices_summary: str,
    news_summary: str,
    market_context: str,
    indicators: dict[str, float | str | None],
    fundamental_summary: str = "",
) -> str:
    """기술적 지표 dict를 해석 텍스트로 변환 후 분석 프롬프트를 생성한다.

    calculate_technical_indicators()의 반환값을 직접 전달하면
    RSI/MACD/BB/추세를 자동 해석하여 프롬프트에 포함한다.

    Args:
        ticker: 종목 코드
        name: 종목명
        prices_summary: 최근 거래일 일별 종가, 변동률, 거래량
        news_summary: 최근 뉴스 헤드라인 + 감성 키워드
        market_context: KOSPI/KOSDAQ 현재 수준
        indicators: calculate_technical_indicators() 반환 dict
        fundamental_summary: 펀더멘탈 요약 텍스트
    """
    technical_summary = _format_technical_summary(indicators)
    return build_analysis_prompt(
        ticker=ticker,
        name=name,
        prices_summary=prices_summary,
        news_summary=news_summary,
        market_context=market_context,
        technical_summary=technical_summary,
        fundamental_summary=fundamental_summary,
    )


def _format_technical_summary(indicators: dict[str, float | str | None]) -> str:
    """기술적 지표 dict를 사람이 읽을 수 있는 텍스트로 변환한다."""
    lines: list[str] = []

    # 기술적 종합 점수
    tech_score = indicators.get("technical_score")
    if tech_score is not None:
        lines.append(f"## 기술적 종합 점수: {tech_score}/10")

    # 이동평균
    sma_parts: list[str] = []
    for key, label in [
        ("sma_5", "5일"),
        ("sma_20", "20일"),
        ("sma_60", "60일"),
        ("sma_120", "120일"),
    ]:
        val = indicators.get(key)
        if val is not None:
            sma_parts.append(f"{label}: {val:,.2f}")
    if sma_parts:
        lines.append(f"- SMA: {', '.join(sma_parts)}")

    ema_parts: list[str] = []
    for key, label in [("ema_12", "12일"), ("ema_26", "26일")]:
        val = indicators.get(key)
        if val is not None:
            ema_parts.append(f"{label}: {val:,.2f}")
    if ema_parts:
        lines.append(f"- EMA: {', '.join(ema_parts)}")

    # RSI
    rsi = indicators.get("rsi_14")
    if rsi is not None:
        rsi_interp = _interpret_rsi(rsi)
        lines.append(f"- RSI(14): {rsi:.2f} ({rsi_interp})")

    # MACD
    macd_val = indicators.get("macd")
    macd_sig = indicators.get("macd_signal")
    macd_hist = indicators.get("macd_hist")
    if macd_val is not None and macd_sig is not None:
        macd_interp = _interpret_macd(macd_val, macd_sig)
        hist_str = f", Histogram: {macd_hist:,.2f}" if macd_hist is not None else ""
        lines.append(
            f"- MACD: {macd_val:,.2f}, Signal: {macd_sig:,.2f}{hist_str} ({macd_interp})"
        )

    # Bollinger Bands
    bb_upper = indicators.get("bb_upper")
    bb_middle = indicators.get("bb_middle")
    bb_lower = indicators.get("bb_lower")
    if bb_upper is not None and bb_lower is not None:
        bb_interp = _interpret_bollinger(indicators)
        lines.append(
            f"- 볼린저밴드: 상단 {bb_upper:,.2f}, "
            f"중단 {bb_middle:,.2f}, 하단 {bb_lower:,.2f} ({bb_interp})"
        )

    # ATR
    atr = indicators.get("atr_14")
    if atr is not None:
        lines.append(f"- ATR(14): {atr:,.2f}")

    # ROC (Rate of Change)
    roc_5 = indicators.get("roc_5")
    roc_20 = indicators.get("roc_20")
    roc_parts: list[str] = []
    if roc_5 is not None:
        roc_parts.append(f"5일: {roc_5:+.2%}")
    if roc_20 is not None:
        roc_parts.append(f"20일: {roc_20:+.2%}")
    if roc_parts:
        lines.append(f"- ROC: {', '.join(roc_parts)}")

    # OBV
    obv = indicators.get("obv")
    if obv is not None:
        lines.append(f"- OBV: {obv:,.0f}")

    # VWAP
    vwap = indicators.get("vwap")
    if vwap is not None:
        lines.append(f"- VWAP(20일): {vwap:,.2f}")

    # 추세/위치
    trend = indicators.get("trend")
    price_pos = indicators.get("price_position")
    if trend is not None:
        trend_kr = {"uptrend": "상승추세", "downtrend": "하락추세", "sideways": "횡보"}
        lines.append(f"- 추세: {trend_kr.get(str(trend), str(trend))}")
    if price_pos is not None:
        pos_kr = {
            "above_ma20": "20일 이평선 위",
            "below_ma20": "20일 이평선 아래",
            "at_ma20": "20일 이평선 부근",
        }
        lines.append(f"- 가격 위치: {pos_kr.get(str(price_pos), str(price_pos))}")

    return "\n".join(lines) if lines else "기술적 지표 데이터 없음"


def _interpret_rsi(rsi: float) -> str:
    """RSI 값을 해석한다."""
    if rsi < 30:
        return "과매도 구간"
    if rsi > 70:
        return "과매수 구간"
    return "중립 구간"


def _interpret_macd(macd: float, signal: float) -> str:
    """MACD와 Signal 관계를 해석한다."""
    if macd > signal:
        return "매수 신호"
    if macd < signal:
        return "매도 신호"
    return "중립"


def _interpret_bollinger(indicators: dict[str, float | str | None]) -> str:
    """볼린저밴드 위치를 해석한다."""
    bb_upper = indicators.get("bb_upper")
    bb_lower = indicators.get("bb_lower")
    sma_20 = indicators.get("sma_20")

    if bb_upper is None or bb_lower is None or sma_20 is None:
        return "판단 불가"

    # sma_20을 현재가 근사치로 사용 (지표 dict에 close가 없으므로)
    # price_position으로 간접 판단
    price_pos = indicators.get("price_position")
    if price_pos == "above_ma20":
        # 상단 밴드 근접 여부는 sma_20과 bb_upper 사이 비율로 추정
        mid_to_upper = float(bb_upper) - float(sma_20)
        if mid_to_upper > 0 and float(sma_20) > float(bb_upper) - mid_to_upper * 0.3:
            return "과매수 영역"
        return "밴드 상단 방향"
    if price_pos == "below_ma20":
        mid_to_lower = float(sma_20) - float(bb_lower)
        if mid_to_lower > 0 and float(sma_20) < float(bb_lower) + mid_to_lower * 0.3:
            return "과매도 영역"
        return "밴드 하단 방향"
    return "밴드 중앙"


def build_market_summary_prompt(
    kr_data: str,
    us_data: str,
    news_headlines: str,
) -> str:
    """일일 시장 요약 프롬프트를 생성한다.

    Args:
        kr_data: 한국 시장 데이터 (KOSPI/KOSDAQ 지수, 변동률 등)
        us_data: 미국 시장 데이터 (S&P500, NASDAQ 등)
        news_headlines: 주요 뉴스 헤드라인
    """
    return f"""\
당신은 글로벌 금융 시장 전문 애널리스트입니다.
오늘의 한국/미국 시장 데이터를 기반으로 일일 시장 요약을 한국어로 작성하세요.

## 한국 시장
{kr_data}

## 미국 시장
{us_data}

## 주요 뉴스
{news_headlines}

아래 항목을 포함하여 구조화된 시장 요약을 작성하세요:
1. 시장 동향 요약
2. 주요 섹터별 동향
3. 글로벌 이슈 및 영향
4. 내일 시장 전망
"""
