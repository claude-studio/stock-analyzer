# Stock Analyzer 개발 로드맵

## 완료된 단계

### MVP (2026-04-16)
- [x] FastAPI + APScheduler 기반 서버 scaffold
- [x] Claude Code Headless (`claude -p`) 래퍼 및 투자 분석 프롬프트
- [x] KRX/US 데이터 수집기 (pykrx, FinanceDataReader, yfinance)
- [x] RSS 뉴스 수집기 (연합인포맥스, 한경, 매경, 이데일리)
- [x] KRX/NYSE 거래일 인식 스케줄러 (APScheduler 3.x)
- [x] SQLAlchemy 2.0 async DB 모델 + Alembic
- [x] Teams Webhook 알림
- [x] OCI ARM 배포 구성 (Dockerfile, docker-compose, Caddy)

### Phase 2: 데이터 파이프라인 완성 (2026-04-16)
- [x] DB 서비스 레이어 (Stock/Price/News/Analysis CRUD, upsert 패턴)
- [x] 스케줄러 잡 5개 DB 연동 완성
- [x] API 라우터 실제 DB 쿼리 연동
- [x] 기술적 지표 계산 엔진 (RSI, MACD, BB, SMA, ATR)
- [x] 프롬프트 FinGPT HG-NC 4단계 구조화

### Critical Fix (2026-04-16)
- [x] NewsArticle.url unique 제약조건 추가
- [x] 뉴스-종목 매칭 엔진 (StockMatcher)
- [x] Claude 분석 파이프라인 정상화 (analyzer.py 활용, market_context 실데이터)
- [x] API Key 인증 + Rate Limiting 미들웨어

### MVP+ (2026-04-16)
- [x] 기술적 지표 Claude 프롬프트 통합
- [x] KRX 수급 데이터 (기관/외국인 순매수) 수집
- [x] 뉴스 감성 분석 (Claude 배치)
- [x] DART 전자공시 수집기 (재무 지표 PER/PBR/ROE)
- [x] Telegram 봇 알림 (buy/strong_buy 자동 전송)
- [x] 일일 시장 요약 리포트 (17:00 KST)
- [x] 추천 적중률 추적 시스템 (7d/30d 평가)

---

## Beta 단계 (다음)

### B1: 멀티 에이전트 분석 (Bull/Bear 토론)
- [ ] Bull 분석가 프롬프트 (성장 가능성, 경쟁 우위, 긍정 시그널 강조)
- [ ] Bear 분석가 프롬프트 (리스크, 약점, 부정 시그널 강조)
- [ ] 토론 종합 판정 (Research Manager 역할)
- [ ] `analysis_type="bull_bear"` 저장
- **참조**: TradingAgents의 Bull/Bear 토론 메커니즘, AI Hedge Fund의 ANALYST_CONFIG 레지스트리

### B2: 백테스팅 프레임워크
- [ ] `BacktestEngine` 클래스 (날짜 범위 + 전략 + 초기 자본)
- [ ] 과거 데이터 기반 매매 시뮬레이션 (일별 루프)
- [ ] 성과 지표 계산 (Sharpe Ratio, Sortino, Max Drawdown, CAGR)
- [ ] SPY/KOSPI 벤치마크 비교
- [ ] API: `POST /api/v1/backtest` -- 백테스트 실행 + 결과 반환
- **참조**: AI Hedge Fund의 BacktestEngine, Qlib의 TopkDropoutStrategy

### B3: 웹 대시보드
- [ ] 프레임워크 선택: Streamlit (빠른 프로토타입) 또는 Next.js (본격 UI)
- [ ] 시장 개요 페이지 (KOSPI/KOSDAQ 지수, 주요 종목 히트맵)
- [ ] 종목 상세 페이지 (차트 + 기술적 지표 + 최근 분석 리포트)
- [ ] 적중률 대시보드 (추천별 통계, 시계열 차트)
- [ ] 포트폴리오 현황 페이지

### B4: Claude CLI -> Anthropic API 전환
- [ ] `anthropic` SDK 직접 사용으로 전환
- [ ] subprocess fork 오버헤드 제거
- [ ] Structured Output (tool_use) 패턴으로 JSON 파싱 안정성 향상
- [ ] 동시 호출 수 확대 (Semaphore 2 -> 5)
- [ ] 비용 추적 (input/output token 카운트)
- **트레이드오프**: Max 구독 무료 사용 포기 -> API 종량제 전환 (월 ~$10-23)

### B5: BM25 메모리 + Reflection 루프
- [ ] `rank_bm25` 기반 과거 분석 유사 상황 검색 (임베딩 API 불필요)
- [ ] 주간 배치: 과거 분석 vs 실제 결과 비교 -> Claude에 "반성문" 요청
- [ ] 반성 결과를 메모리에 저장 -> 이후 분석 시 유사 상황 컨텍스트로 주입
- **참조**: TradingAgents의 `memory.py` BM25Okapi, `reflection.py` Reflector

### B6: 데이터 이상치 탐지 + 이벤트 처리
- [ ] 가격 검증 레이어 (전일 대비 +/-30% 이상 변동 시 경고)
- [ ] 서킷브레이커/거래정지 종목 자동 필터링
- [ ] 액면분할/무상증자 시 수정주가 보정
- [ ] pykrx `adjusted=True` 옵션 활성화

---

## v1.0 단계

### V1: 포트폴리오 관리
- [ ] 보유 종목 등록 (종목, 수량, 매입가)
- [ ] 포트폴리오 수익률/MDD 실시간 추적
- [ ] PyPortfolioOpt 기반 리밸런싱 제안 (Max Sharpe, HRP, Risk Parity)
- [ ] 섹터/국가 분산도 시각화
- [ ] API: `GET /api/v1/portfolios/{id}/optimize`

### V2: 조건 알림 시스템
- [ ] 가격 도달 알림 (목표가/손절가)
- [ ] 기술적 지표 조건 알림 (RSI < 30, MACD 골든크로스 등)
- [ ] 감성 급변 알림 (sentiment_score 급락)
- [ ] 수급 급변 알림 (외국인 대량 매도 등)
- [ ] 알림 규칙 CRUD API

### V3: 증권사 API 연동
- [ ] 한국투자증권 Open API 연동 (잔고/체결/주문 조회)
- [ ] 실시간 시세 WebSocket 연결
- [ ] 원클릭 매매 (분석 결과 -> 주문 실행)
- [ ] 주문 이력 추적 + 실현 손익 계산

### V4: 고급 분석
- [ ] 섹터 로테이션 분석 (업종별 상대강도)
- [ ] 매크로 지표 통합 (금리, 환율, 유가, VIX)
- [ ] 재무제표 PDF 파싱 + RAG 기반 심층 분석
- [ ] 뉴스 클러스터링 (BERTopic) + dissemination breadth 측정
- [ ] 일목균형표, Stochastic, ADX 등 추가 기술적 지표

---

## 인프라 개선 (Phase 무관, 필요 시)

- [ ] Redis 캐시 실제 활용 (현재 컨테이너만 존재)
- [ ] APScheduler job store를 PostgreSQL로 전환 (재시작 시 misfire 보장)
- [ ] 헬스체크에 DB/Redis ping 추가
- [ ] 테스트 작성 (현재 0줄)
- [ ] Alembic 초기 마이그레이션 생성
- [ ] Dockerfile Claude CLI 버전 고정
- [ ] CORS 설정
- [ ] Pydantic response_model 정의
- [ ] 잡 함수 보일러플레이트 데코레이터 추출

---

## 기술 참조 (오픈소스)

| 프로젝트 | 차용 패턴 |
|---|---|
| AI Hedge Fund (55k stars) | ANALYST_CONFIG 레지스트리, 정량+LLM 하이브리드, BacktestEngine |
| TradingAgents (50.7k stars) | Bull/Bear 토론, BM25 메모리, Reflection 루프 |
| OpenBB (65.9k stars) | TET Fetcher 패턴, Provider 플러그인 시스템 |
| Qlib (40.7k stars) | Alpha158 팩터, TopkDropout 전략, Expression 트리 |
| FinGPT (19.4k stars) | HG-NC 구조화 프롬프트, RAPTOR RAG |
