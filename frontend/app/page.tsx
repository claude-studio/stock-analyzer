import { fetchAPI } from "@/lib/api";
import type { MarketOverview, HealthStatus } from "@/lib/api";

async function getMarketOverview() {
  try {
    return await fetchAPI<MarketOverview>("/api/v1/market/overview");
  } catch {
    return null;
  }
}

async function getHealthStatus() {
  try {
    return await fetchAPI<HealthStatus>("/health");
  } catch {
    return null;
  }
}

function formatNumber(n: number): string {
  return n.toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function ChangeIndicator({ value, pct }: { value: number; pct: number }) {
  const isUp = value > 0;
  const isFlat = value === 0;
  const color = isFlat ? "text-gray-400" : isUp ? "text-green-500" : "text-red-500";
  const arrow = isFlat ? "" : isUp ? "+" : "";
  return (
    <span className={`text-sm font-medium ${color} tabular-nums`}>
      {arrow}{formatNumber(value)} ({arrow}{pct.toFixed(2)}%)
    </span>
  );
}

export default async function DashboardPage() {
  const [market, health] = await Promise.all([
    getMarketOverview(),
    getHealthStatus(),
  ]);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">대시보드</h1>
        <p className="mt-1 text-sm text-gray-400">시장 개요 및 시스템 상태</p>
      </div>

      {/* 시장 지수 카드 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div className="rounded-lg border border-gray-800 bg-[#111111] p-5">
          <p className="text-sm font-medium text-gray-400">KOSPI</p>
          {market ? (
            <div className="mt-2">
              <p className="text-2xl font-semibold tabular-nums">
                {formatNumber(market.kospi.value)}
              </p>
              <ChangeIndicator value={market.kospi.change} pct={market.kospi.change_pct} />
            </div>
          ) : (
            <p className="mt-2 text-sm text-gray-500">데이터를 불러올 수 없습니다</p>
          )}
        </div>

        <div className="rounded-lg border border-gray-800 bg-[#111111] p-5">
          <p className="text-sm font-medium text-gray-400">KOSDAQ</p>
          {market ? (
            <div className="mt-2">
              <p className="text-2xl font-semibold tabular-nums">
                {formatNumber(market.kosdaq.value)}
              </p>
              <ChangeIndicator value={market.kosdaq.change} pct={market.kosdaq.change_pct} />
            </div>
          ) : (
            <p className="mt-2 text-sm text-gray-500">데이터를 불러올 수 없습니다</p>
          )}
        </div>

        <div className="rounded-lg border border-gray-800 bg-[#111111] p-5">
          <p className="text-sm font-medium text-gray-400">시스템 상태</p>
          <div className="mt-2">
            {health ? (
              <div className="flex items-center gap-2">
                <span
                  className={`inline-block h-2.5 w-2.5 rounded-full ${
                    health.status === "ok" ? "bg-green-500" : "bg-red-500"
                  }`}
                />
                <span className="text-sm font-medium">
                  {health.status === "ok" ? "정상 운영 중" : "점검 필요"}
                </span>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <span className="inline-block h-2.5 w-2.5 rounded-full bg-gray-500" />
                <span className="text-sm text-gray-500">연결 불가</span>
              </div>
            )}
            {health?.scheduler_running !== undefined && (
              <p className="mt-1 text-xs text-gray-500">
                스케줄러: {health.scheduler_running ? "실행 중" : "중지됨"}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* 최근 분석 알림 */}
      <div>
        <h2 className="text-lg font-semibold">최근 분석</h2>
        <div className="mt-4 rounded-lg border border-gray-800 bg-[#111111] p-6">
          <p className="text-sm text-gray-400">
            API 서버에 연결되면 최근 분석 결과가 여기에 표시됩니다.
          </p>
        </div>
      </div>
    </div>
  );
}
