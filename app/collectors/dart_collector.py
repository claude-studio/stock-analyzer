"""DART 전자공시 + 재무제표 수집기 (opendartreader)."""

import asyncio
from datetime import date, datetime
from zoneinfo import ZoneInfo

import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)
KST = ZoneInfo("Asia/Seoul")

# corp_code 캐시 (같은 세션 내 중복 조회 방지)
_corp_code_cache: dict[str, str | None] = {}

# quarter -> reprt_code 매핑
_QUARTER_TO_REPRT_CODE: dict[int, str] = {
    1: "11013",  # 1분기보고서
    2: "11012",  # 반기보고서
    3: "11014",  # 3분기보고서
    4: "11011",  # 사업보고서
}

# 재무제표 핵심 계정과목 매핑
_ACCOUNT_NAME_MAP: dict[str, str] = {
    "매출액": "revenue",
    "수익(매출액)": "revenue",
    "영업이익": "operating_income",
    "영업이익(손실)": "operating_income",
    "당기순이익": "net_income",
    "당기순이익(손실)": "net_income",
    "기본주당이익(손실)": "eps",
    "기본주당순이익(손실)": "eps",
}


def _get_dart_reader():
    """OpenDartReader 인스턴스를 생성한다. API 키가 없으면 None."""
    if not settings.DART_API_KEY:
        return None
    import OpenDartReader
    return OpenDartReader.OpenDartReader(settings.DART_API_KEY)


def _parse_amount(value: str | int | float | None) -> int | None:
    """재무제표 금액 문자열을 정수로 파싱한다."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    cleaned = str(value).replace(",", "").replace(" ", "").strip()
    if not cleaned or cleaned == "-":
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def _get_latest_quarter(ref_date: date) -> tuple[int, int]:
    """현재 월 기준 최근 확정 분기를 반환한다.

    Returns:
        (year, quarter) 튜플. 공시 시차를 고려하여 한 분기 이전을 반환.
    """
    month = ref_date.month
    year = ref_date.year
    if month <= 3:
        # 1분기 이전 -> 전년도 3분기
        return year - 1, 3
    if month <= 6:
        # 2분기 이전 -> 전년도 사업보고서
        return year - 1, 4
    if month <= 9:
        # 3분기 이전 -> 당해 1분기
        return year, 1
    # 4분기 이전 -> 당해 반기
    return year, 2


def _collect_today_disclosures_sync(target_date: date) -> list[dict]:
    """당일 공시 목록을 동기로 수집한다."""
    dart = _get_dart_reader()
    if dart is None:
        logger.info("dart_api_key_not_set", action="skip_disclosures")
        return []

    date_str = target_date.strftime("%Y%m%d")
    logger.info("dart_disclosures_collecting", date=date_str)

    df = dart.list(start=date_str, end=date_str, kind="A")

    if df is None or df.empty:
        logger.info("dart_disclosures_empty", date=date_str)
        return []

    records = df.to_dict("records")
    logger.info("dart_disclosures_collected", date=date_str, count=len(records))
    return records


async def collect_today_disclosures(target_date: date | None = None) -> list[dict]:
    """당일 공시 목록 수집.

    Args:
        target_date: 수집 대상 날짜. None이면 오늘(KST 기준).

    Returns:
        [{"corp_name", "report_nm", "rcept_no", "rcept_dt", "corp_code"}, ...]
    """
    if target_date is None:
        target_date = datetime.now(tz=KST).date()
    return await asyncio.to_thread(_collect_today_disclosures_sync, target_date)


def _collect_financial_summary_sync(
    corp_code: str, year: int, quarter: int
) -> dict | None:
    """기업 재무 지표 요약을 동기로 조회한다."""
    dart = _get_dart_reader()
    if dart is None:
        logger.info("dart_api_key_not_set", action="skip_financial_summary")
        return None

    reprt_code = _QUARTER_TO_REPRT_CODE.get(quarter)
    if reprt_code is None:
        logger.warning("dart_invalid_quarter", quarter=quarter)
        return None

    logger.info(
        "dart_finstate_collecting",
        corp_code=corp_code,
        year=year,
        reprt_code=reprt_code,
    )

    try:
        df = dart.finstate(corp_code, year, reprt_code=reprt_code)
    except Exception as e:
        logger.warning(
            "dart_finstate_failed",
            corp_code=corp_code,
            year=year,
            reprt_code=reprt_code,
            error=str(e),
        )
        return None

    if df is None or df.empty:
        logger.info(
            "dart_finstate_empty",
            corp_code=corp_code,
            year=year,
            reprt_code=reprt_code,
        )
        return None

    result: dict[str, int | None] = {
        "revenue": None,
        "operating_income": None,
        "net_income": None,
        "eps": None,
    }

    for _, row in df.iterrows():
        account_nm = row.get("account_nm", "")
        field_key = _ACCOUNT_NAME_MAP.get(account_nm)
        if field_key is None:
            continue
        if result[field_key] is not None:
            continue
        result[field_key] = _parse_amount(row.get("thstrm_amount"))

    logger.info(
        "dart_finstate_collected",
        corp_code=corp_code,
        year=year,
        quarter=quarter,
        result=result,
    )
    return result


async def collect_financial_summary(
    corp_code: str, year: int, quarter: int
) -> dict | None:
    """기업 재무 지표 요약 조회.

    Args:
        corp_code: DART 기업 고유번호.
        year: 사업연도.
        quarter: 분기 (1~4).

    Returns:
        {"revenue", "operating_income", "net_income", "eps"}
        조회 실패 시 None.
    """
    return await asyncio.to_thread(
        _collect_financial_summary_sync, corp_code, year, quarter
    )


def _get_corp_code_sync(ticker: str) -> str | None:
    """종목코드로 DART corp_code를 동기로 조회한다."""
    if ticker in _corp_code_cache:
        return _corp_code_cache[ticker]

    dart = _get_dart_reader()
    if dart is None:
        logger.info("dart_api_key_not_set", action="skip_corp_code")
        _corp_code_cache[ticker] = None
        return None

    try:
        corp_code = dart.find_corp_code(ticker)
    except Exception as e:
        logger.warning(
            "dart_corp_code_lookup_failed",
            ticker=ticker,
            error=str(e),
        )
        _corp_code_cache[ticker] = None
        return None

    if not corp_code:
        logger.info("dart_corp_code_not_found", ticker=ticker)
        _corp_code_cache[ticker] = None
        return None

    _corp_code_cache[ticker] = corp_code
    logger.info("dart_corp_code_resolved", ticker=ticker, corp_code=corp_code)
    return corp_code


async def get_corp_code(ticker: str) -> str | None:
    """종목코드 -> DART corp_code 변환.

    Args:
        ticker: 종목코드 (예: "005930").

    Returns:
        DART 기업 고유번호. 조회 실패 시 None.
    """
    return await asyncio.to_thread(_get_corp_code_sync, ticker)


async def collect_fundamentals_for_watchlist(
    tickers: list[str],
) -> dict[str, dict]:
    """관심 종목 재무 지표 일괄 조회.

    Args:
        tickers: 종목코드 리스트 (예: ["005930", "000660"]).

    Returns:
        {"005930": {"revenue": ..., "operating_income": ..., ...}, ...}
        실패한 종목은 결과에서 제외.
    """
    if not settings.DART_API_KEY:
        logger.info("dart_api_key_not_set", action="skip_watchlist_fundamentals")
        return {}

    today = datetime.now(tz=KST).date()
    year, quarter = _get_latest_quarter(today)
    logger.info(
        "dart_watchlist_fundamentals_start",
        tickers=tickers,
        year=year,
        quarter=quarter,
    )

    results: dict[str, dict] = {}
    for ticker in tickers:
        corp_code = await get_corp_code(ticker)
        if corp_code is None:
            logger.warning("dart_watchlist_skip_no_corp_code", ticker=ticker)
            continue

        summary = await collect_financial_summary(corp_code, year, quarter)
        if summary is None:
            logger.warning(
                "dart_watchlist_skip_no_financials",
                ticker=ticker,
                corp_code=corp_code,
            )
            continue

        results[ticker] = summary

    logger.info(
        "dart_watchlist_fundamentals_done",
        total=len(tickers),
        collected=len(results),
    )
    return results
