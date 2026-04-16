#!/usr/bin/env bash
set -euo pipefail

echo "=== Stock Analyzer - OCI ARM Setup ==="

# 1. PostgreSQL: stock_analysis DB + 유저 생성
echo "[1/4] PostgreSQL 설정..."
docker exec boj-postgres psql -U boj -d bojmemorial -c "
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'stock') THEN
        CREATE ROLE stock WITH LOGIN PASSWORD 'stock_pass';
    END IF;
END
\$\$;
" 2>/dev/null

docker exec boj-postgres psql -U boj -d bojmemorial -c "
SELECT 'CREATE DATABASE stock_analysis OWNER stock'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'stock_analysis')
\gexec
" 2>/dev/null

echo "  DB stock_analysis 준비 완료"

# 2. Docker 네트워크 확인
echo "[2/4] Docker 네트워크 확인..."
if ! docker network inspect infra_default >/dev/null 2>&1; then
    echo "  WARNING: infra_default 네트워크가 없습니다. 기존 infra docker-compose를 먼저 실행하세요."
    exit 1
fi
echo "  infra_default 네트워크 확인됨"

# 3. Claude Code 인증 확인
echo "[3/4] Claude Code 인증 확인..."
if claude --version >/dev/null 2>&1; then
    echo "  Claude Code $(claude --version) 설치됨"
    if [ -d "$HOME/.claude" ]; then
        echo "  인증 정보 존재"
    else
        echo "  WARNING: Claude 인증이 필요합니다."
        echo "  실행: claude login"
        echo "  (브라우저 URL이 출력되면 로컬에서 열어 인증하세요)"
    fi
else
    echo "  ERROR: Claude Code가 설치되지 않았습니다."
    echo "  실행: npm install -g @anthropic-ai/claude-code"
    exit 1
fi

# 4. .env 파일 확인
echo "[4/4] 환경변수 확인..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "  .env 파일 생성됨 -- 값을 수정해주세요!"
else
    echo "  .env 파일 존재"
fi

echo ""
echo "=== Setup 완료 ==="
echo ""
echo "다음 단계:"
echo "  1. .env 파일 수정 (DART_API_KEY, TEAMS_WEBHOOK_URL 등)"
echo "  2. Claude 인증: claude login"
echo "  3. 서비스 시작: docker compose up -d --build"
echo "  4. DB 마이그레이션: docker exec stock-api alembic upgrade head"
echo "  5. 헬스체크: curl http://localhost:8000/health"
