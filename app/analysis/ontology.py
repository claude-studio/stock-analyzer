"""종목 관계 온톨로지 생성 및 관리."""

import asyncio
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.claude_runner import ClaudeRunner
from app.collectors.dart_collector import _get_dart_reader, get_corp_code
from app.database.models import Stock, StockRelation
from app.service.db_service import get_stock_by_ticker, upsert_stock_relation

logger = structlog.get_logger(__name__)
KST = ZoneInfo("Asia/Seoul")

RELATION_TYPES = ["competitor", "supplier", "customer", "affiliate", "sector_peer", "investment"]

RELATION_SEED_PROMPT = """다음 종목의 주요 관계사를 분석하라.

종목: {name} ({ticker})
업종: {sector}

관계 유형:
- competitor: 직접 경쟁사 (같은 제품/서비스)
- supplier: 이 종목에 부품/원재료를 공급하는 기업
- customer: 이 종목이 납품하는 주요 고객사
- affiliate: 같은 기업집단/계열사
- sector_peer: 같은 섹터의 동종 기업 (경쟁까지는 아닌)

JSON 배열로만 응답. 한국 상장사 중심으로, 비상장/해외 기업은 상장된 경우만 포함.
최대 15개 관계까지.

형식:
[
  {{"target_name": "SK하이닉스", "target_ticker": "000660", "type": "competitor", "strength": 0.9, "context": "DRAM/NAND 반도체 직접 경쟁"}},
  ...
]
"""


async def generate_relation_seed(
    runner: ClaudeRunner,
    ticker: str,
    name: str,
    sector: str,
) -> list[dict]:
    """Claude로 종목 관계 시드를 생성한다."""
    prompt = RELATION_SEED_PROMPT.format(
        name=name, ticker=ticker, sector=sector or "미분류",
    )
    result = await runner.run(prompt, output_format="json")

    if isinstance(result, list):
        return result
    if isinstance(result, str):
        match = re.search(r"\[.*\]", result, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                logger.warning("relation_seed_parse_failed", ticker=ticker)
    return []


async def build_relation_context(
    session: AsyncSession,
    stock_id: int,
) -> str:
    """DB에서 종목 관계를 조회하여 프롬프트용 텍스트를 생성한다."""
    stmt = (
        select(StockRelation, Stock.name)
        .join(Stock, StockRelation.target_stock_id == Stock.id)
        .where(StockRelation.source_stock_id == stock_id)
        .order_by(StockRelation.strength.desc().nulls_last())
    )
    result = await session.execute(stmt)
    rows = result.all()

    if not rows:
        return ""

    # 관계 유형별로 그룹핑
    by_type: dict[str, list[str]] = {}
    type_labels = {
        "competitor": "경쟁",
        "supplier": "공급업체",
        "customer": "고객사",
        "affiliate": "계열사",
        "sector_peer": "동종업",
    }
    for rel, target_name in rows:
        label = type_labels.get(rel.relation_type, rel.relation_type)
        strength_str = f" {float(rel.strength):.1f}" if rel.strength else ""
        entry = f"{target_name}{strength_str}"
        by_type.setdefault(label, []).append(entry)

    parts: list[str] = []
    for rel_label, entries in by_type.items():
        parts.append(f"{rel_label}({', '.join(entries)})")

    return " / ".join(parts)


async def build_relation_context_for_watchlist(
    session: AsyncSession,
    watchlist: list[str],
) -> str:
    """워치리스트 전체 종목의 관계 컨텍스트를 한번에 생성한다."""
    lines: list[str] = []

    for ticker in watchlist:
        stock_stmt = select(Stock).where(Stock.ticker == ticker)
        stock_result = await session.execute(stock_stmt)
        stock = stock_result.scalar_one_or_none()
        if not stock:
            continue

        ctx = await build_relation_context(session, stock.id)
        if ctx:
            lines.append(f"- {stock.name}({ticker}): {ctx}")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# Task 1: DART 타법인출자/최대주주 현황에서 계열사 관계 수집
# ──────────────────────────────────────────────


def _collect_dart_affiliates_sync(corp_code: str, corp_name: str) -> list[dict]:
    """DART에서 계열사/투자 관계를 동기로 수집한다.

    dart.report()의 key_nm은 정확한 값이 문서에 명확히 규정되어 있지 않으므로
    여러 후보를 시도하고, 모두 실패하면 빈 리스트를 반환한다.
    """
    dart = _get_dart_reader()
    if dart is None:
        return []

    year = datetime.now(tz=KST).year - 1
    results: list[dict] = []

    # report()로 타법인출자 현황 시도
    report_keys = [
        "타법인 출자 현황",
        "타법인출자 현황(상세)",
        "타법인출자현황(상세)",
    ]
    df = None
    for key_nm in report_keys:
        try:
            df = dart.report(corp_code, key_nm, year)
            if df is not None and not df.empty:
                break
            df = None
        except Exception:
            df = None

    if df is not None and not df.empty:
        for _, row in df.iterrows():
            target_name = str(row.get("inv_prm", row.get("법인명", ""))).strip()
            if not target_name or target_name == corp_name:
                continue

            # 지분율 파싱
            pct_raw = row.get("owne_prti", row.get("지분율", row.get("소유비율", None)))
            pct = _parse_pct(pct_raw)
            if pct is None or pct < 5.0:
                continue

            rel_type = "affiliate" if pct >= 20.0 else "investment"
            results.append({
                "target_name": target_name,
                "type": rel_type,
                "strength": min(pct / 100.0, 1.0),
                "context": f"지분 {pct:.1f}% 보유",
                "ownership_pct": pct,
            })

        logger.info(
            "dart_affiliates_collected",
            corp_code=corp_code,
            count=len(results),
            method="report",
        )
    else:
        logger.info(
            "dart_affiliates_no_data",
            corp_code=corp_code,
            year=year,
        )

    return results


def _parse_pct(value: object) -> float | None:
    """지분율 값을 float(%)로 파싱한다."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace("%", "").replace(",", "").strip()
    if not cleaned or cleaned == "-":
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


async def collect_dart_affiliates(ticker: str) -> list[dict]:
    """DART 타법인출자현황에서 계열사/투자 관계를 수집한다.

    Returns:
        [{"target_name": str, "type": "affiliate"|"investment",
          "strength": float, "context": str, "ownership_pct": float}, ...]
    """
    corp_code = await get_corp_code(ticker)
    if not corp_code:
        return []

    # corp_name 조회 (자기 자신 필터링용)
    dart = _get_dart_reader()
    corp_name = ""
    if dart is not None:
        try:
            corp_name = dart.corp(corp_code).get("corp_name", "")
        except Exception:
            pass

    return await asyncio.to_thread(_collect_dart_affiliates_sync, corp_code, corp_name)


async def seed_from_dart(session: AsyncSession, tickers: list[str]) -> int:
    """DART API에서 사실 기반 관계를 수집하여 stock_relations에 저장한다.

    source='dart'로 표시하여 LLM 생성 관계와 구분.
    """
    # ticker -> stock 매핑 구축
    ticker_to_stock: dict[str, Stock] = {}
    all_stocks_by_name: dict[str, int] = {}

    for ticker in tickers:
        stock = await get_stock_by_ticker(session, ticker)
        if stock:
            ticker_to_stock[ticker] = stock

    # 전체 종목의 name -> id 매핑 (타겟 매칭용)
    name_result = await session.execute(
        select(Stock.name, Stock.id).where(Stock.is_active.is_(True))
    )
    for row in name_result:
        all_stocks_by_name[row.name] = row.id

    seeded = 0
    for ticker, stock in ticker_to_stock.items():
        try:
            affiliates = await collect_dart_affiliates(ticker)
            for aff in affiliates:
                target_name = aff["target_name"]
                # 타겟 종목 매칭: 정확 이름 매칭
                target_id = all_stocks_by_name.get(target_name)
                if not target_id:
                    # 부분 매칭 시도 (종목명에 법인명이 포함된 경우)
                    for sname, sid in all_stocks_by_name.items():
                        if target_name in sname or sname in target_name:
                            target_id = sid
                            break

                if not target_id or target_id == stock.id:
                    continue

                rel_type = aff["type"]
                if rel_type not in ("affiliate", "investment"):
                    rel_type = "affiliate"

                await upsert_stock_relation(
                    session,
                    source_stock_id=stock.id,
                    target_stock_id=target_id,
                    relation_type=rel_type,
                    strength=aff["strength"],
                    context=aff["context"],
                    source="dart",
                )
                seeded += 1

            logger.info("dart_seed_done", ticker=ticker, relations=len(affiliates), matched=seeded)
        except Exception:
            logger.warning("dart_seed_failed", ticker=ticker, exc_info=True)

        await asyncio.sleep(1)

    return seeded


# ──────────────────────────────────────────────
# Task 2: sector 기반 sector_peer 관계 배치 생성
# ──────────────────────────────────────────────


async def seed_sector_peers(session: AsyncSession) -> int:
    """Stock 테이블의 sector 필드를 기반으로 같은 업종 종목을 sector_peer로 연결한다.

    source='sector_map'으로 표시.
    """
    from app.core.config import settings

    watchlist = settings.KR_WATCHLIST

    # 워치리스트 종목 조회
    watchlist_stocks: list[Stock] = []
    for ticker in watchlist:
        stock = await get_stock_by_ticker(session, ticker)
        if stock and stock.sector:
            watchlist_stocks.append(stock)

    if not watchlist_stocks:
        return 0

    # 워치리스트 종목의 sector 목록
    sectors = {s.sector for s in watchlist_stocks if s.sector}

    # 같은 sector의 활성 종목 조회 (워치리스트 외 포함, sector당 상위 20개)
    sector_stocks: dict[str, list[Stock]] = {}
    for sector in sectors:
        stmt = (
            select(Stock)
            .where(Stock.sector == sector, Stock.is_active.is_(True))
            .order_by(Stock.id)
            .limit(20)
        )
        result = await session.execute(stmt)
        sector_stocks[sector] = list(result.scalars().all())

    seeded = 0
    # 워치리스트 종목 간 + 워치리스트 -> 같은 섹터 종목
    for stock in watchlist_stocks:
        if not stock.sector:
            continue

        peers = sector_stocks.get(stock.sector, [])
        for peer in peers:
            if peer.id == stock.id:
                continue

            await upsert_stock_relation(
                session,
                source_stock_id=stock.id,
                target_stock_id=peer.id,
                relation_type="sector_peer",
                strength=1.0,
                context=f"KRX 업종 분류: {stock.sector}",
                source="sector_map",
            )
            seeded += 1

    logger.info("sector_peers_seeded", count=seeded)
    return seeded


# ──────────────────────────────────────────────
# Task 3: LLM 시드를 별도 함수로 분리
# ──────────────────────────────────────────────


async def seed_from_llm(
    session: AsyncSession,
    runner: ClaudeRunner,
    tickers: list[str],
) -> int:
    """Claude로 경쟁사/공급망 등 사실 데이터로 커버 안 되는 관계를 보충한다.

    이미 sector_peer/affiliate/dart 소스로 존재하는 관계는 스킵한다.
    """
    from app.service.db_service import get_stock_name_map

    stock_name_map = await get_stock_name_map(session)
    ticker_to_id: dict[str, int] = {}
    name_to_id: dict[str, int] = {}
    for key, sid in stock_name_map.items():
        if len(key) <= 10:
            ticker_to_id[key] = sid
        name_to_id[key] = sid

    seeded = 0
    for ticker in tickers:
        stock = await get_stock_by_ticker(session, ticker)
        if not stock:
            continue

        # 이미 존재하는 관계 조회 (중복 방지)
        existing_stmt = (
            select(StockRelation.target_stock_id, StockRelation.relation_type)
            .where(StockRelation.source_stock_id == stock.id)
        )
        existing_result = await session.execute(existing_stmt)
        existing_pairs = {(row[0], row[1]) for row in existing_result}

        try:
            seeds = await generate_relation_seed(
                runner, ticker, stock.name, stock.sector or "",
            )
            for seed in seeds:
                target_ticker = seed.get("target_ticker", "")
                target_name = seed.get("target_name", "")
                target_id = ticker_to_id.get(target_ticker) or name_to_id.get(target_name)
                if not target_id:
                    continue

                rel_type = seed.get("type", "sector_peer")
                if rel_type not in (
                    "competitor", "supplier", "customer", "affiliate", "sector_peer",
                ):
                    rel_type = "sector_peer"

                # 이미 사실 기반으로 존재하면 스킵
                if (target_id, rel_type) in existing_pairs:
                    continue

                await upsert_stock_relation(
                    session,
                    source_stock_id=stock.id,
                    target_stock_id=target_id,
                    relation_type=rel_type,
                    strength=seed.get("strength"),
                    context=seed.get("context"),
                    source="llm",
                )
                seeded += 1

            logger.info("llm_seed_done", ticker=ticker, count=len(seeds))
        except (RuntimeError, TimeoutError):
            logger.warning("llm_seed_failed", ticker=ticker, exc_info=True)

        await asyncio.sleep(2)

    return seeded
