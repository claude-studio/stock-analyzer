# Stock Analyzer

Claude Code Headless 기반 주식 분석 서버.
OCI ARM Free Tier에서 구동되며, Max 구독의 Claude Code CLI로 투자 분석 리포트를 자동 생성한다.

## 아키텍처

- **FastAPI** -- API 서버 + APScheduler 기반 자동 수집
- **Claude Code CLI** -- `claude -p` headless 모드로 투자 분석 실행
- **PostgreSQL** -- 기존 boj-postgres 인스턴스에 stock_analysis DB 추가
- **Redis** -- 캐시

## 기술 스택

| 구분 | 선택 |
|---|---|
| Runtime | Python 3.12, ARM64 |
| Web | FastAPI + uvicorn |
| DB | PostgreSQL 16 + SQLAlchemy 2.0 async |
| Cache | Redis 7 |
| Scheduler | APScheduler 3.x |
| LLM | Claude Code CLI (Max 구독) |
| KRX Data | pykrx + FinanceDataReader |
| US Data | yfinance |
| News | RSS (연합인포맥스, 한경, 매경, 이데일리) |

## 주요 기능

- **자동 데이터 수집**: KRX/US OHLCV, 수급(기관/외국인 순매수), RSS 뉴스, DART 공시
- **기술적 지표**: RSI, MACD, 볼린저밴드, SMA, EMA, ATR 자동 계산
- **Claude AI 분석**: 기술적 지표 + 수급 + 감성 + 펀더멘탈 4단계 구조화 프롬프트
- **감성 분석**: Claude 배치 감성 분석 (positive/negative/neutral)
- **Telegram 알림**: buy/strong_buy 종목 자동 알림 + 일일 시장 요약
- **적중률 추적**: 7일/30일 예측 vs 실제 주가 비교 평가
- **DART 공시**: 재무 지표(PER/PBR/ROE) 자동 조회

## 수집 스케줄 (KST)

| 시각 | 작업 |
|---|---|
| 07:00 | 적중률 평가 (7d/30d 분석 적중 여부) |
| 08:00, 12:00, 16:00 | 뉴스 수집 + 감성 분석 |
| 08:30 | 장 전 준비 (종목 리스트 갱신) |
| 15:35 | KRX 장 마감 OHLCV + 수급 수집 |
| 16:10 | DART 공시 수집 + 재무 지표 |
| 16:30 | Claude 투자 분석 -> Telegram 알림 |
| 17:00 | 일일 시장 요약 리포트 -> Telegram |
| 05:30 | 미국 장 마감 OHLCV 수집 |

## 배포

```bash
# OCI ARM 서버에서
cd /home/ubuntu/stock-analyzer
bash deploy/setup.sh
docker compose up -d --build
docker exec stock-api alembic upgrade head
```

## API

| 엔드포인트 | 설명 | 인증 |
|---|---|---|
| `GET /health` | 서비스 상태 + 스케줄러 잡 목록 | 불필요 |
| `GET /api/v1/stocks` | 종목 목록 (market 필터) | X-API-Key |
| `GET /api/v1/stocks/{ticker}/prices` | 가격 히스토리 | X-API-Key |
| `GET /api/v1/stocks/{ticker}/analysis` | 최근 분석 리포트 | X-API-Key |
| `GET /api/v1/accuracy` | 추천 적중률 통계 | X-API-Key |
| `POST /api/v1/stocks/{ticker}/analysis/request` | 온디맨드 분석 트리거 | X-API-Key + Rate Limit |

## 로드맵

자세한 개발 계획은 [docs/ROADMAP.md](docs/ROADMAP.md) 참조.

## 면책 조항

이 프로젝트는 **개인 학습 및 정보 제공 목적**으로 개발되었습니다.

- 이 도구의 분석 결과는 **투자 조언, 추천, 매매 권유에 해당하지 않습니다**
- 투자 의사결정의 **최종 책임은 사용자에게** 있습니다
- LLM 기반 분석은 환각(hallucination), 편향, 수학적 오류를 포함할 수 있습니다
- 과거 분석 적중률은 미래 성과를 보장하지 않습니다
- 실제 투자 전 **자격을 갖춘 투자 전문가와 상담**을 권장합니다

## 로컬 개발

```bash
pip install -e ".[dev]"
cp .env.example .env
# .env 수정
uvicorn app.main:app --reload
```
