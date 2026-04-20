"""뉴스 제목/요약에서 종목명/종목코드를 추출하여 매칭하는 모듈."""

import structlog

logger = structlog.get_logger(__name__)

# 오탐 방지: 2글자 이하 종목명은 무시
_MIN_NAME_LENGTH = 3


class StockMatcher:
    """종목명/종목코드 기반 뉴스-종목 매칭 엔진."""

    def __init__(self, stock_map: dict[str, int]) -> None:
        """stock_map: {종목명: stock_id, 종목코드: stock_id} 매핑."""
        self._name_map: dict[str, int] = {}
        for key, stock_id in stock_map.items():
            if len(key) >= _MIN_NAME_LENGTH:
                self._name_map[key] = stock_id
        # 긴 종목명 우선 매칭 (카카오뱅크 > 카카오)
        self._sorted_names = sorted(
            self._name_map.keys(), key=len, reverse=True
        )

    def match(self, text: str) -> list[int]:
        """텍스트에서 매칭되는 stock_id 리스트 반환 (복수 매칭, 정확 매칭 우선)."""
        if not text:
            return []

        exact: list[int] = []
        partial: list[int] = []
        seen_ids: set[int] = set()

        for name in self._sorted_names:
            stock_id = self._name_map[name]
            if stock_id in seen_ids:
                continue

            if name == text:
                exact.append(stock_id)
                seen_ids.add(stock_id)
            elif name in text:
                partial.append(stock_id)
                seen_ids.add(stock_id)

        return exact + partial
