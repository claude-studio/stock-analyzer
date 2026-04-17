"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { fetchAPI } from "@/lib/api";
import type { Stock, AnalysisReport, DailyPrice } from "@/lib/api";
import StockChartWrapper from "@/components/charts/StockChartWrapper";

function RecommendationBadge({ recommendation }: { recommendation: string }) {
  const lower = recommendation.toLowerCase();
  let bgColor = "bg-gray-700";
  let textColor = "text-gray-300";
  let label = recommendation;

  if (lower.includes("strong_buy")) { bgColor = "bg-green-600"; textColor = "text-white"; label = "강력 매수"; }
  else if (lower.includes("buy")) { bgColor = "bg-green-500/15"; textColor = "text-green-400"; label = "매수"; }
  else if (lower.includes("strong_sell")) { bgColor = "bg-red-600"; textColor = "text-white"; label = "강력 매도"; }
  else if (lower.includes("sell")) { bgColor = "bg-red-500/15"; textColor = "text-red-400"; label = "매도"; }
  else if (lower.includes("hold")) { bgColor = "bg-yellow-500/15"; textColor = "text-yellow-400"; label = "보유"; }

  return (
    <span className={`inline-flex items-center rounded-md px-2.5 py-1 text-xs font-semibold ${bgColor} ${textColor}`}>
      {label}
    </span>
  );
}

export default function StockDetailPage() {
  const params = useParams();
  const ticker = params.ticker as string;

  const [stock, setStock] = useState<Stock | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisReport | null>(null);
  const [latestPrice, setLatestPrice] = useState<DailyPrice | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!ticker) return;
    Promise.all([
      fetchAPI<{ stocks: Stock[] }>(`/api/v1/stocks?limit=1&offset=0`).then(r => r.stocks.find(s => s.ticker === ticker) || null).catch(() => null),
      fetchAPI<{ ticker: string; analysis: AnalysisReport | null }>(`/api/v1/stocks/${ticker}/analysis`).then(r => r.analysis).catch(() => null),
      fetchAPI<{ prices: DailyPrice[] }>(`/api/v1/stocks/${ticker}/prices?limit=1`).then(r => r.prices[0] || null).catch(() => null),
    ]).then(([s, a, p]) => {
      setStock(s);
      setAnalysis(a);
      setLatestPrice(p);
      setLoading(false);
    });
  }, [ticker]);

  if (loading) {
    return <div className="text-sm text-gray-400">로딩 중...</div>;
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">{stock?.name ?? ticker}</h1>
            <span className="rounded bg-gray-800 px-2 py-0.5 font-mono text-sm text-gray-400">{ticker}</span>
          </div>
          {stock && (
            <p className="mt-1 text-sm text-gray-400">{stock.market} {stock.sector ? `/ ${stock.sector}` : ""}</p>
          )}
        </div>
        {latestPrice && (
          <div className="text-right">
            <p className="text-3xl font-semibold tabular-nums">{latestPrice.close.toLocaleString("ko-KR")}</p>
            <p className="text-xs text-gray-500">{latestPrice.trade_date} 종가</p>
          </div>
        )}
      </div>

      <div className="rounded-lg border border-gray-800 bg-[#111111] p-6">
        <p className="text-sm font-medium text-gray-400 mb-4">가격 차트</p>
        <StockChartWrapper ticker={ticker} />
      </div>

      {analysis ? (
        <div className="space-y-6">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-semibold">AI 분석 리포트</h2>
            <RecommendationBadge recommendation={analysis.recommendation} />
          </div>

          <div className="rounded-lg border border-gray-800 bg-[#111111] p-5">
            <p className="text-sm leading-relaxed text-gray-300">{analysis.summary}</p>
            <div className="mt-4 flex flex-wrap gap-4 text-sm">
              <div>
                <span className="text-gray-500">신뢰도</span>{" "}
                <span className="font-medium tabular-nums">{(analysis.confidence * 100).toFixed(0)}%</span>
              </div>
              {analysis.target_price && (
                <div>
                  <span className="text-gray-500">목표가</span>{" "}
                  <span className="font-medium tabular-nums">{analysis.target_price.toLocaleString("ko-KR")}</span>
                </div>
              )}
              <div>
                <span className="text-gray-500">분석일</span>{" "}
                <span className="font-medium">{analysis.analysis_date}</span>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {analysis.bull_case && (
              <div className="rounded-lg border border-green-500/20 bg-green-500/5 p-5">
                <p className="text-sm font-medium text-green-400 mb-2">Bull Case</p>
                <p className="text-sm leading-relaxed text-gray-300">{analysis.bull_case}</p>
              </div>
            )}
            {analysis.bear_case && (
              <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-5">
                <p className="text-sm font-medium text-red-400 mb-2">Bear Case</p>
                <p className="text-sm leading-relaxed text-gray-300">{analysis.bear_case}</p>
              </div>
            )}
          </div>

          {analysis.key_factors && analysis.key_factors.length > 0 && (
            <div className="rounded-lg border border-gray-800 bg-[#111111] p-5">
              <p className="text-sm font-medium text-gray-400 mb-3">핵심 요인</p>
              <ul className="space-y-2">
                {analysis.key_factors.map((factor, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-gray-300">
                    <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-gray-500" />
                    {factor}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ) : (
        <div className="rounded-lg border border-gray-800 bg-[#111111] p-6">
          <p className="text-sm text-gray-400">아직 분석 리포트가 없습니다.</p>
          <p className="mt-1 text-xs text-gray-500">16:30 스케줄러가 실행되면 자동으로 생성됩니다.</p>
        </div>
      )}
    </div>
  );
}
