"use client";

import { useEffect, useState } from "react";
import { fetchAPI } from "@/lib/api";

interface MarketData {
  kospi: { close: number; change_pct: number } | null;
  kosdaq: { close: number; change_pct: number } | null;
}

interface HealthData {
  status: string;
  checks: Record<string, string>;
  jobs: { id: string; next_run: string }[];
}

export default function DashboardPage() {
  const [market, setMarket] = useState<MarketData | null>(null);
  const [health, setHealth] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetchAPI<MarketData>("/api/v1/market/overview").catch(() => null),
      fetchAPI<HealthData>("/health").catch(() => null),
    ]).then(([m, h]) => {
      setMarket(m);
      setHealth(h);
      setLoading(false);
    });
  }, []);

  if (loading) {
    return (
      <div className="space-y-8">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">대시보드</h1>
          <p className="mt-1 text-sm text-gray-400">로딩 중...</p>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-28 animate-pulse rounded-lg border border-gray-800 bg-gray-900" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">대시보드</h1>
        <p className="mt-1 text-sm text-gray-400">시장 개요 및 시스템 상태</p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div className="rounded-lg border border-gray-800 bg-[#111111] p-5">
          <p className="text-sm font-medium text-gray-400">KOSPI</p>
          {market?.kospi?.close ? (
            <div className="mt-2">
              <p className="text-2xl font-semibold tabular-nums">
                {market.kospi.close.toLocaleString("ko-KR", { minimumFractionDigits: 2 })}
              </p>
              <span className={`text-sm font-medium tabular-nums ${market.kospi.change_pct >= 0 ? "text-green-500" : "text-red-500"}`}>
                {market.kospi.change_pct >= 0 ? "+" : ""}{market.kospi.change_pct.toFixed(2)}%
              </span>
            </div>
          ) : (
            <p className="mt-2 text-sm text-gray-500">장 마감 후 데이터가 표시됩니다</p>
          )}
        </div>

        <div className="rounded-lg border border-gray-800 bg-[#111111] p-5">
          <p className="text-sm font-medium text-gray-400">KOSDAQ</p>
          {market?.kosdaq?.close ? (
            <div className="mt-2">
              <p className="text-2xl font-semibold tabular-nums">
                {market.kosdaq.close.toLocaleString("ko-KR", { minimumFractionDigits: 2 })}
              </p>
              <span className={`text-sm font-medium tabular-nums ${market.kosdaq.change_pct >= 0 ? "text-green-500" : "text-red-500"}`}>
                {market.kosdaq.change_pct >= 0 ? "+" : ""}{market.kosdaq.change_pct.toFixed(2)}%
              </span>
            </div>
          ) : (
            <p className="mt-2 text-sm text-gray-500">장 마감 후 데이터가 표시됩니다</p>
          )}
        </div>

        <div className="rounded-lg border border-gray-800 bg-[#111111] p-5">
          <p className="text-sm font-medium text-gray-400">시스템 상태</p>
          <div className="mt-2">
            {health ? (
              <>
                <div className="flex items-center gap-2">
                  <span className={`inline-block h-2.5 w-2.5 rounded-full ${health.status === "ok" ? "bg-green-500" : "bg-yellow-500"}`} />
                  <span className="text-sm font-medium">
                    {health.status === "ok" ? "정상 운영 중" : health.status}
                  </span>
                </div>
                <p className="mt-1 text-xs text-gray-500">
                  등록 잡: {health.jobs.length}개
                </p>
              </>
            ) : (
              <div className="flex items-center gap-2">
                <span className="inline-block h-2.5 w-2.5 rounded-full bg-red-500" />
                <span className="text-sm text-gray-500">API 서버 연결 실패</span>
              </div>
            )}
          </div>
        </div>
      </div>

      <div>
        <h2 className="text-lg font-semibold">스케줄 현황</h2>
        {health?.jobs && health.jobs.length > 0 ? (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="py-2 text-left font-medium text-gray-400">잡 이름</th>
                  <th className="py-2 text-left font-medium text-gray-400">다음 실행</th>
                </tr>
              </thead>
              <tbody>
                {health.jobs.map((job) => (
                  <tr key={job.id} className="border-b border-gray-800/50">
                    <td className="py-2 font-mono text-gray-300">{job.id}</td>
                    <td className="py-2 tabular-nums text-gray-400">{job.next_run}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="mt-4 rounded-lg border border-gray-800 bg-[#111111] p-6">
            <p className="text-sm text-gray-400">API 서버에 연결되면 스케줄 현황이 표시됩니다.</p>
          </div>
        )}
      </div>
    </div>
  );
}
