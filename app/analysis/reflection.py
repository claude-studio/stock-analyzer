"""주간 Reflection 루프 모듈.

매주 금요일 적중률을 분석하고 편향 패턴을 식별하여 개선점을 도출한다.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.accuracy import get_accuracy_stats
from app.analysis.claude_runner import ClaudeRunner
from app.utils.discord import send_alert

logger = structlog.get_logger(__name__)
KST = ZoneInfo("Asia/Seoul")

REFLECTION_LOG_PATH = Path(__file__).parent / "reflection_log.json"

_REFLECTION_PROMPT_TEMPLATE = """\
당신은 투자 분석 시스템의 메타 분석가입니다.
아래는 최근 90일간의 추천 적중률 통계입니다.

## 전체 통계
- 총 평가 건수: {total}
- 7일 적중률: {hit_rate_7d:.1%} (적중 {hit_7d} / 미적중 {miss_7d})
- 30일 적중률: {hit_rate_30d:.1%} (적중 {hit_30d} / 미적중 {miss_30d})

## 추천 유형별 적중률
{by_recommendation_text}

## 분석 요청
1. 적중률 40% 이하인 추천 유형에 대해 편향 패턴을 분석하세요.
2. 과매수/과매도 신호 무시, 뉴스 과잉 반응 등 체계적 편향이 있는지 식별하세요.
3. 개선을 위한 구체적 제안을 3가지 이내로 제시하세요.

JSON 형식으로 응답하세요:
{{
  "bias_analysis": "편향 분석 결과",
  "weak_areas": ["취약 영역 1", "취약 영역 2"],
  "improvements": ["개선 제안 1", "개선 제안 2", "개선 제안 3"]
}}
"""


async def run_weekly_reflection(
    runner: ClaudeRunner,
    session: AsyncSession,
) -> str:
    """주간 Reflection을 실행한다.

    1. get_accuracy_stats(session, days=90)로 적중률 통계
    2. recommendation별 적중률 분석
    3. 적중률 40% 이하 유형에 대해 Claude에 편향 분석 요청
    4. 결과를 reflection_log.json에 append
    5. Discord에 reflection 결과 요약 전송

    Returns:
        reflection 결과 요약 텍스트
    """
    stats = await get_accuracy_stats(session, days=90)

    # 추천 유형별 텍스트 생성
    by_rec = stats.get("by_recommendation", {})
    rec_lines: list[str] = []
    low_accuracy_types: list[str] = []

    for rec_type, rec_stats in by_rec.items():
        hit_rate = rec_stats.get("hit_rate_7d", 0.0)
        count = rec_stats.get("count", 0)
        rec_lines.append(f"- {rec_type}: 7일 적중률 {hit_rate:.1%} (건수: {count})")
        if hit_rate < 0.4 and count >= 3:
            low_accuracy_types.append(rec_type)

    by_recommendation_text = "\n".join(rec_lines) if rec_lines else "데이터 없음"

    # 적중률이 전반적으로 낮거나 특정 유형이 취약하면 Claude 분석 요청
    if stats.get("total", 0) < 5:
        summary = "평가 데이터가 부족하여 Reflection을 건너뜁니다."
        logger.info("reflection_skipped", reason="insufficient_data", total=stats.get("total", 0))
        return summary

    prompt = _REFLECTION_PROMPT_TEMPLATE.format(
        total=stats["total"],
        hit_rate_7d=stats["hit_rate_7d"],
        hit_7d=stats["hit_7d"],
        miss_7d=stats["miss_7d"],
        hit_rate_30d=stats["hit_rate_30d"],
        hit_30d=stats["hit_30d"],
        miss_30d=stats["miss_30d"],
        by_recommendation_text=by_recommendation_text,
    )

    try:
        result = await runner.run(prompt, output_format="json")
    except (RuntimeError, TimeoutError) as e:
        logger.warning("reflection_claude_failed", error=str(e))
        return f"Reflection Claude 호출 실패: {e}"

    # 결과 파싱
    reflection_data: dict = {}
    if isinstance(result, dict):
        reflection_data = result
    elif isinstance(result, str):
        try:
            reflection_data = json.loads(result)
        except json.JSONDecodeError:
            reflection_data = {"bias_analysis": result, "weak_areas": [], "improvements": []}

    # reflection_log.json에 append
    log_entry = {
        "timestamp": datetime.now(tz=KST).isoformat(),
        "stats": stats,
        "low_accuracy_types": low_accuracy_types,
        "reflection": reflection_data,
    }
    _append_reflection_log(log_entry)

    # Discord 알림
    summary_lines = [
        f"7일 적중률: {stats['hit_rate_7d']:.1%}",
        f"30일 적중률: {stats['hit_rate_30d']:.1%}",
    ]
    if low_accuracy_types:
        summary_lines.append(f"취약 유형: {', '.join(low_accuracy_types)}")

    bias = reflection_data.get("bias_analysis", "")
    if bias:
        summary_lines.append(f"편향 분석: {bias[:200]}")

    improvements = reflection_data.get("improvements", [])
    if improvements:
        summary_lines.append("개선 제안:")
        for imp in improvements[:3]:
            summary_lines.append(f"  - {imp}")

    summary = "\n".join(summary_lines)

    try:
        await send_alert(
            title="주간 Reflection 결과",
            message=summary,
            color=0x9B59B6,
        )
    except Exception:
        logger.warning("reflection_discord_failed", exc_info=True)

    logger.info(
        "reflection_completed",
        total=stats["total"],
        hit_rate_7d=stats["hit_rate_7d"],
        low_accuracy_types=low_accuracy_types,
    )

    return summary


def _append_reflection_log(entry: dict) -> None:
    """reflection_log.json에 항목을 추가한다."""
    logs: list[dict] = []
    if REFLECTION_LOG_PATH.exists():
        try:
            logs = json.loads(REFLECTION_LOG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logs = []

    logs.append(entry)

    # 최대 52주(1년) 분량만 유지
    if len(logs) > 52:
        logs = logs[-52:]

    REFLECTION_LOG_PATH.write_text(
        json.dumps(logs, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
