# Changelog

## [0.2.0] - 2026-04-20

프로덕트 개선 Phase A+B: 데이터 수집 품질 개선 + 분석 엔진 고도화

### Added
- **멀티 분석가 시스템**: 가치(0.35)/모멘텀(0.35)/감성(0.30) 3명 분석가 독립 분석 후 가중 평균 종합 (`analyst_config.py`)
- **BM25 메모리**: rank_bm25 기반 과거 분석 유사 검색, 신규 분석 시 컨텍스트 주입 (`memory.py`)
- **주간 Reflection 루프**: 매주 금요일 18:00 적중률 편향 분석 + 개선 제안 자동 생성 (`reflection.py`)
- **기술적 팩터 확장**: ROC(5/20일), OBV, VWAP 추가 + 종합 스코어(0-10)
- **OHLCV 급변동 검증**: 전일 대비 50% 이상 변동 시 warning (액면분할 의심)
- **`get_stock_name_map()`**: 종목명+ticker 통합 매핑 함수 (`db_service.py`)
- **`get_past_analyses()`**: 90일 AnalysisReport + AccuracyTracker 조인 조회 (`db_service.py`)

### Changed
- **stock_matcher**: ticker 기반 -> 종목명 기반 매칭으로 전환, 복수 매칭 지원, 긴 이름 우선
- **프롬프트 연결**: `jobs.py`에서 `build_analysis_prompt_with_indicators()` 직접 호출로 교체 (기존 수동 합산 제거)
- **Bull/Bear 분석**: SYSTEM_PROMPT에 순차 독립 작성 지시 추가 (사후 합리화 편향 완화)
- **감성 점수**: 양수 전용(0~1) -> 방향 반영(-1.0 ~ +1.0) 정규화
- **수집기 재시도**: KRX/US/DART 수집기에 3회 재시도 + 지수 백오프(2/4/8초) 추가

### Fixed
- `target_price` 가드레일: 음수/0 거부, `confidence` 0.95 클램프, `key_factors` 빈 배열 방어
- `job_news_collect`: 2개 쿼리(`get_stock_id_map` + 별도 name 조회) -> `get_stock_name_map` 단일 호출

### Dependencies
- `rank-bm25>=0.2.2` 추가 (순수 Python, ARM 완전 호환)

---

## [0.1.0] - 2026-04-17

초기 릴리스: MVP + MVP+ + 프론트엔드 대시보드 + OCI ARM 배포

### Added
- FastAPI + APScheduler 기반 자동 수집 서버
- Claude Code Headless 투자 분석 (FinGPT HG-NC 4단계 프롬프트)
- KRX/US OHLCV, 수급(기관/외국인), RSS 뉴스, DART 공시 수집
- 기술적 지표 계산 (RSI, MACD, BB, SMA, EMA, ATR)
- Claude 감성 분석 + 적중률 추적 (7d/30d)
- Discord Webhook 알림 (buy/strong_buy + 일일 시장 요약)
- Next.js 15 대시보드 (캔들차트, 워치리스트, 뉴스, 적중률)
- Docker + Caddy + Alembic 배포 구성
