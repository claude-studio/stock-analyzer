"""분석 실행 및 결과 파싱."""

import json
import re

import pandas as pd
import structlog
from pydantic import BaseModel, Field, field_validator

from app.analysis.claude_runner import ClaudeRunner
from app.analysis.prompts import (
    build_analysis_prompt,
    build_analysis_prompt_with_indicators,
    build_market_summary_prompt,
)

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

    @field_validator("target_price")
    @classmethod
    def target_price_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("target_price는 양수여야 합니다")
        return v

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return min(v, 0.95)

    @field_validator("key_factors")
    @classmethod
    def ensure_key_factors(cls, v: list[str]) -> list[str]:
        if not v:
            return ["분석 요인 미제공"]
        return v


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
    indicators: dict | None = None,
    fundamental_summary: str = "",
    system_prompt_addon: str = "",
    past_analyses_text: str = "",
) -> AnalysisResult:
    """종목 분석을 실행하고 결과를 반환한다.

    Args:
        runner: ClaudeRunner 인스턴스
        ticker: 종목 코드
        name: 종목명
        prices_df: 가격 데이터 DataFrame
        news_list: 뉴스 목록 (title, sentiment 키 포함)
        market_ctx: 시장 컨텍스트 문자열
        indicators: 기술적 지표 dict (calculate_technical_indicators 반환값)
        fundamental_summary: 펀더멘탈 요약 텍스트
        system_prompt_addon: 시스템 프롬프트에 추가할 텍스트 (분석가별 지침)
        past_analyses_text: BM25 과거 분석 참조 텍스트

    Returns:
        AnalysisResult 파싱된 분석 결과

    Raises:
        ValueError: 결과 파싱 실패 시
    """
    prices_summary = _build_prices_summary(prices_df)
    news_summary = _build_news_summary(news_list)

    if indicators:
        prompt = build_analysis_prompt_with_indicators(
            ticker=ticker,
            name=name,
            prices_summary=prices_summary,
            news_summary=news_summary,
            market_context=market_ctx,
            indicators=indicators,
            fundamental_summary=fundamental_summary,
        )
    else:
        prompt = build_analysis_prompt(
            ticker=ticker,
            name=name,
            prices_summary=prices_summary,
            news_summary=news_summary,
            market_context=market_ctx,
            fundamental_summary=fundamental_summary,
        )

    if system_prompt_addon:
        prompt = f"{system_prompt_addon}\n\n{prompt}"

    if past_analyses_text:
        prompt = f"{prompt}\n\n{past_analyses_text}"

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


async def run_multi_analysis(
    runner: ClaudeRunner,
    ticker: str,
    name: str,
    prices_df: pd.DataFrame,
    news_list: list[dict],
    market_ctx: str,
    indicators: dict | None = None,
    fundamental_summary: str = "",
    session: "AsyncSession | None" = None,
) -> tuple[AnalysisResult, dict[str, AnalysisResult]]:
    """멀티 분석가 시스템으로 종합 분석을 실행한다.

    ANALYST_CONFIG의 각 분석가(가치/모멘텀/감성)로 순차 Claude 호출 후
    weight 기반 가중 평균으로 종합 결과를 생성한다.

    Args:
        runner: ClaudeRunner 인스턴스
        ticker: 종목 코드
        name: 종목명
        prices_df: 가격 데이터 DataFrame
        news_list: 뉴스 목록
        market_ctx: 시장 컨텍스트 문자열
        indicators: 기술적 지표 dict
        fundamental_summary: 펀더멘탈 요약 텍스트
        session: DB 세션 (BM25 메모리 조회용)

    Returns:
        (종합 결과, {분석가 유형: 개별 결과} dict)
    """
    from app.analysis.analyst_config import ANALYST_CONFIG
    from app.analysis.memory import AnalysisMemory

    # BM25 과거 분석 메모리 구축
    past_analyses_text = ""
    if session is not None:
        try:
            from app.service.db_service import get_past_analyses

            past_reports = await get_past_analyses(session, days=90)
            if past_reports:
                memory = AnalysisMemory()
                memory.build_corpus(past_reports)
                query = f"{ticker} {name}"
                similar = memory.search_similar(query, top_k=3)
                if similar:
                    lines = ["## 과거 유사 분석 참조"]
                    for s in similar:
                        lines.append(
                            f"- [{s.get('ticker', '')}] {s.get('recommendation', '')}: "
                            f"{s.get('summary', '')[:100]} "
                            f"(적중률: {s.get('hit_rate', 0):.0%})"
                        )
                    past_analyses_text = "\n".join(lines)
        except Exception:
            logger.warning("bm25_memory_load_failed", ticker=ticker, exc_info=True)

    individual_results: dict[str, AnalysisResult] = {}

    # 각 분석가를 순차 실행 (Semaphore 제한 때문에 의도된 순차 실행)
    for analyst_type, config in ANALYST_CONFIG.items():
        try:
            result = await run_stock_analysis(
                runner=runner,
                ticker=ticker,
                name=name,
                prices_df=prices_df,
                news_list=news_list,
                market_ctx=market_ctx,
                indicators=indicators,
                fundamental_summary=fundamental_summary,
                system_prompt_addon=config["system_prompt_addon"],
                past_analyses_text=past_analyses_text,
            )
            individual_results[analyst_type] = result
            logger.info(
                "analyst_completed",
                ticker=ticker,
                analyst=analyst_type,
                recommendation=result.recommendation,
            )
        except (ValueError, RuntimeError, TimeoutError) as e:
            logger.warning(
                "analyst_failed",
                ticker=ticker,
                analyst=analyst_type,
                error=str(e),
            )

    if not individual_results:
        raise ValueError(f"모든 분석가가 실패했습니다: {ticker}")

    # 가중 평균 종합
    combined = _combine_analyst_results(individual_results, ANALYST_CONFIG)
    return combined, individual_results


def _combine_analyst_results(
    results: dict[str, AnalysisResult],
    config: dict[str, dict],
) -> AnalysisResult:
    """개별 분석가 결과를 가중 평균으로 종합한다."""
    # recommendation 다수결
    rec_votes: dict[str, float] = {}
    total_weight = 0.0
    weighted_confidence = 0.0
    weighted_target = 0.0
    all_factors: list[str] = []
    bull_parts: list[str] = []
    bear_parts: list[str] = []
    summaries: list[str] = []

    for analyst_type, result in results.items():
        weight = config.get(analyst_type, {}).get("weight", 1.0 / len(results))
        analyst_name = config.get(analyst_type, {}).get("name", analyst_type)

        rec_votes[result.recommendation] = rec_votes.get(result.recommendation, 0.0) + weight
        weighted_confidence += result.confidence * weight
        weighted_target += result.target_price * weight
        total_weight += weight

        all_factors.extend(result.key_factors)
        bull_parts.append(f"[{analyst_name}] {result.bull_case}")
        bear_parts.append(f"[{analyst_name}] {result.bear_case}")
        summaries.append(f"[{analyst_name}] {result.summary}")

    # 다수결 recommendation
    best_rec = max(rec_votes, key=rec_votes.get)

    # 중복 제거된 key_factors
    seen: set[str] = set()
    unique_factors: list[str] = []
    for f in all_factors:
        if f not in seen:
            seen.add(f)
            unique_factors.append(f)

    return AnalysisResult(
        summary=" / ".join(summaries),
        recommendation=best_rec,
        confidence=weighted_confidence / total_weight if total_weight else 0.5,
        target_price=weighted_target / total_weight if total_weight else 0.0,
        bull_case=" | ".join(bull_parts),
        bear_case=" | ".join(bear_parts),
        key_factors=unique_factors[:10],
    )


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
