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

    def match(self, text: str) -> list[int]:
        """텍스트에서 매칭되는 stock_id 리스트 반환 (첫 번째 매칭만)."""
        if not text:
            return []
        for name, stock_id in self._name_map.items():
            if name in text:
                return [stock_id]
        return []
