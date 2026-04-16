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

## 수집 스케줄 (KST)

| 시각 | 작업 |
|---|---|
| 08:30 | 장 전 준비 (종목 리스트 갱신) |
| 08:00, 12:00, 16:00 | 뉴스 수집 |
| 15:35 | KRX 장 마감 OHLCV 수집 |
| 16:30 | Claude 투자 분석 리포트 생성 |
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

- `GET /health` -- 서비스 상태 + 스케줄러 잡 목록
- `GET /api/v1/stocks` -- 종목 목록
- `GET /api/v1/stocks/{ticker}/prices` -- 가격 히스토리
- `GET /api/v1/stocks/{ticker}/analysis` -- 최근 분석 리포트
- `POST /api/v1/stocks/{ticker}/analysis/request` -- 온디맨드 분석 트리거

## 로컬 개발

```bash
pip install -e ".[dev]"
cp .env.example .env
# .env 수정
uvicorn app.main:app --reload
```
