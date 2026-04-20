"""종목 관계 온톨로지 생성 및 관리."""

import json
import re

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.claude_runner import ClaudeRunner
from app.database.models import Stock, StockRelation

logger = structlog.get_logger(__name__)

RELATION_TYPES = ["competitor", "supplier", "customer", "affiliate", "sector_peer"]

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
