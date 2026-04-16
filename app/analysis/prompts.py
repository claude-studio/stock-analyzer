"""투자 분석 프롬프트 템플릿."""

SYSTEM_PROMPT: str = """\
당신은 한국/미국 주식 시장 전문 투자 분석가입니다.
제공된 데이터를 기반으로 종목에 대한 투자 분석을 수행하세요.

반드시 아래 JSON 구조로만 응답하세요. 다른 텍스트는 포함하지 마세요.

{
  "summary": "종합 분석 요약 (2-3문장)",
  "recommendation": "strong_buy | buy | hold | sell | strong_sell",
  "confidence": 0.0-1.0 사이의 확신도,
  "target_price": 목표가 (숫자),
  "bull_case": "상승 시나리오 설명",
  "bear_case": "하락 시나리오 설명",
  "key_factors": ["핵심 요인 1", "핵심 요인 2", ...]
}

모든 응답은 한국어로 작성하세요.
"""


def build_analysis_prompt(
    ticker: str,
    name: str,
    prices_summary: str,
    news_summary: str,
    market_context: str,
) -> str:
    """종목 분석용 프롬프트를 조합한다.

    Args:
        ticker: 종목 코드
        name: 종목명
        prices_summary: 최근 5거래일 종가, 변동률, 거래량
        news_summary: 최근 뉴스 헤드라인 5개 + 감성 키워드
        market_context: KOSPI/KOSDAQ 현재 수준
    """
    return f"""{SYSTEM_PROMPT}

## 분석 대상
- 종목코드: {ticker}
- 종목명: {name}

## 최근 주가 데이터 (5거래일)
{prices_summary}

## 최근 뉴스 및 감성 분석
{news_summary}

## 시장 컨텍스트
{market_context}

위 데이터를 종합하여 투자 분석 결과를 JSON으로 응답하세요.
"""


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
