"""최근 뉴스 영향 관측 반응 백필 스크립트."""

import argparse
import asyncio

import structlog

from app.database.session import async_session_factory
from app.service.db_service import refresh_news_observed_reactions

logger = structlog.get_logger(__name__)


async def _run(days: int, dry_run: bool) -> None:
    async with async_session_factory() as session:
        stats = await refresh_news_observed_reactions(session, days=days, dry_run=dry_run)
        if dry_run:
            await session.rollback()
        else:
            await session.commit()
        logger.info("news_impact_backfill_finished", days=days, dry_run=dry_run, **stats)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="뉴스 영향 관측 반응을 최근 N일 범위로 백필합니다.",
    )
    parser.add_argument("--days", type=int, default=90, help="백필 대상 기간(일)")
    parser.add_argument("--dry-run", action="store_true", help="DB 변경 없이 대상 건수만 확인")
    args = parser.parse_args()
    asyncio.run(_run(days=args.days, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
