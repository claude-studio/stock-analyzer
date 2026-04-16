"""분석 실행 및 결과 파싱."""

import json
import re

import pandas as pd
import structlog
from pydantic import BaseModel, Field

from app.analysis.claude_runner import ClaudeRunner
from app.analysis.prompts import build_analysis_prompt, build_market_summary_prompt

logger = structlog.get_logger(__name__)


class AnalysisResult(BaseModel):
    """종목 분석 결과 모델."""

    summary: str
    recommendation: str = Field(
        pattern=r"^(strong_buy|buy|hold|sell|strong_sell)$",
    )
    confidence: float = Field(ge=0.0, le=1.0)
    target_price: float
    bull_case: str
    bear_case: str
    key_factors: list[str]


def _extract_json_from_text(text: str) -> dict | None:
    """raw 텍스트에서 JSON 블록을 추출 시도한다."""
    # ```json ... ``` 블록 추출
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 첫 번째 { ... } 블록 추출
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None


def _build_prices_summary(prices_df: pd.DataFrame) -> str:
    """DataFrame에서 가격 요약 문자열을 생성한다."""
    if prices_df.empty:
        return "가격 데이터 없음"

    recent = prices_df.tail(5)
    lines = []
    for _, row in recent.iterrows():
        date = row.get("date", row.name)
        close = row.get("close", "N/A")
        change = row.get("change_pct", "N/A")
        volume = row.get("volume", "N/A")
        lines.append(f"- {date}: 종가 {close}, 변동률 {change}%, 거래량 {volume}")
    return "\n".join(lines)


def _build_news_summary(news_list: list[dict]) -> str:
    """뉴스 리스트에서 요약 문자열을 생성한다."""
    if not news_list:
        return "관련 뉴스 없음"

    lines = []
    for news in news_list[:5]:
        title = news.get("title", "")
        sentiment = news.get("sentiment", "")
        lines.append(f"- {title} (감성: {sentiment})")
    return "\n".join(lines)


async def run_stock_analysis(
    runner: ClaudeRunner,
    ticker: str,
    name: str,
    prices_df: pd.DataFrame,
    news_list: list[dict],
    market_ctx: str,
) -> AnalysisResult:
    """종목 분석을 실행하고 결과를 반환한다.

    Args:
        runner: ClaudeRunner 인스턴스
        ticker: 종목 코드
        name: 종목명
        prices_df: 가격 데이터 DataFrame
        news_list: 뉴스 목록 (title, sentiment 키 포함)
        market_ctx: 시장 컨텍스트 문자열

    Returns:
        AnalysisResult 파싱된 분석 결과

    Raises:
        ValueError: 결과 파싱 실패 시
    """
    prices_summary = _build_prices_summary(prices_df)
    news_summary = _build_news_summary(news_list)

    prompt = build_analysis_prompt(
        ticker=ticker,
        name=name,
        prices_summary=prices_summary,
        news_summary=news_summary,
        market_context=market_ctx,
    )

    logger.info("stock_analysis_start", ticker=ticker, name=name)

    result = await runner.run(prompt, output_format="json")

    # JSON 포맷으로 받은 경우 직접 파싱
    if isinstance(result, dict):
        try:
            return AnalysisResult.model_validate(result)
        except Exception as e:
            logger.warning(
                "analysis_result_validation_failed",
                ticker=ticker,
                error=str(e),
            )

    # 문자열인 경우 JSON 추출 시도
    if isinstance(result, str):
        extracted = _extract_json_from_text(result)
        if extracted:
            try:
                return AnalysisResult.model_validate(extracted)
            except Exception as e:
                logger.warning(
                    "analysis_result_extraction_failed",
                    ticker=ticker,
                    error=str(e),
                )

    raise ValueError(f"분석 결과를 파싱할 수 없습니다: {ticker}")


async def run_market_summary(
    runner: ClaudeRunner,
    kr_data: str,
    us_data: str,
    news: str,
) -> str:
    """일일 시장 요약을 실행한다.

    Args:
        runner: ClaudeRunner 인스턴스
        kr_data: 한국 시장 데이터
        us_data: 미국 시장 데이터
        news: 주요 뉴스 헤드라인

    Returns:
        시장 요약 텍스트
    """
    prompt = build_market_summary_prompt(
        kr_data=kr_data,
        us_data=us_data,
        news_headlines=news,
    )

    logger.info("market_summary_start")

    result = await runner.run(prompt, output_format="text")

    if isinstance(result, dict):
        return json.dumps(result, ensure_ascii=False, indent=2)

    return result
