"""BM25 기반 과거 분석 메모리 모듈."""

from __future__ import annotations

import re

import structlog

logger = structlog.get_logger(__name__)


def _tokenize(text: str) -> list[str]:
    """간단한 한국어/영어 토큰화."""
    text = text.lower()
    tokens = re.findall(r"[가-힣]+|[a-z0-9]+", text)
    return tokens


class AnalysisMemory:
    """과거 분석 보고서를 BM25로 검색하는 메모리 시스템."""

    def __init__(self) -> None:
        self._corpus: list[list[str]] = []
        self._metadata: list[dict] = []
        self._bm25 = None

    def build_corpus(self, reports: list[dict]) -> None:
        """과거 분석 보고서로 BM25 코퍼스를 구축한다.

        Args:
            reports: [{"summary": str, "key_factors": list, "recommendation": str,
                       "ticker": str, "hit_rate": float}, ...]
        """
        from rank_bm25 import BM25Okapi

        self._corpus = []
        self._metadata = []

        for report in reports:
            summary = report.get("summary", "")
            factors = report.get("key_factors", [])
            ticker = report.get("ticker", "")
            recommendation = report.get("recommendation", "")

            if isinstance(factors, list):
                factors_text = " ".join(factors)
            else:
                factors_text = str(factors) if factors else ""

            doc_text = f"{ticker} {recommendation} {summary} {factors_text}"
            tokens = _tokenize(doc_text)

            if tokens:
                self._corpus.append(tokens)
                self._metadata.append(report)

        if self._corpus:
            self._bm25 = BM25Okapi(self._corpus)
            logger.info("bm25_corpus_built", doc_count=len(self._corpus))
        else:
            self._bm25 = None
            logger.info("bm25_corpus_empty")

    def search_similar(self, query: str, top_k: int = 3) -> list[dict]:
        """BM25로 유사 과거 분석을 검색한다.

        Args:
            query: 검색 쿼리 (종목코드 + 종목명 등)
            top_k: 반환할 최대 결과 수

        Returns:
            유사도 순으로 정렬된 과거 분석 리포트 목록
        """
        if self._bm25 is None or not self._corpus:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        scores = self._bm25.get_scores(query_tokens)

        # 상위 top_k개 인덱스
        scored_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True,
        )[:top_k]

        results: list[dict] = []
        for idx in scored_indices:
            if scores[idx] > 0:
                results.append(self._metadata[idx])

        return results
