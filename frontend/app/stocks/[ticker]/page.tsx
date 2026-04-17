import dynamic from "next/dynamic";
import { fetchAPI } from "@/lib/api";
import type { Stock, AnalysisReport, DailyPrice } from "@/lib/api";

const StockChart = dynamic(
  () => import("@/components/charts/StockChart"),
  { ssr: false },
);

interface PageProps {
  params: Promise<{ ticker: string }>;
}

async function getStock(ticker: string) {
  try {
    return await fetchAPI<Stock>(`/api/v1/stocks/${ticker}`);
  } catch {
    return null;
  }
}

async function getAnalysis(ticker: string) {
  try {
    return await fetchAPI<AnalysisReport>(`/api/v1/stocks/${ticker}/analysis`);
  } catch {
    return null;
  }
}

async function getLatestPrice(ticker: string) {
  try {
    const prices = await fetchAPI<DailyPrice[]>(`/api/v1/stocks/${ticker}/prices?limit=1`);
    return prices[0] ?? null;
  } catch {
    return null;
  }
}

function RecommendationBadge({ recommendation }: { recommendation: string }) {
  const lower = recommendation.toLowerCase();
  let bgColor = "bg-gray-700";
  let textColor = "text-gray-300";

  if (lower.includes("buy") || lower.includes("매수")) {
    bgColor = "bg-green-500/15";
    textColor = "text-green-400";
  } else if (lower.includes("sell") || lower.includes("매도")) {
    bgColor = "bg-red-500/15";
    textColor = "text-red-400";
  } else if (lower.includes("hold") || lower.includes("보유")) {
    bgColor = "bg-yellow-500/15";
    textColor = "text-yellow-400";
  }

  return (
    <span className={`inline-flex items-center rounded-md px-2.5 py-1 text-xs font-semibold ${bgColor} ${textColor}`}>
      {recommendation}
    </span>
  );
}

export default async function StockDetailPage({ params }: PageProps) {
  const { ticker } = await params;
  const [stock, analysis, latestPrice] = await Promise.all([
    getStock(ticker),
    getAnalysis(ticker),
    getLatestPrice(ticker),
  ]);

  return (
    <div className="space-y-8">
      {/* 헤더 */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">
              {stock?.name ?? ticker}
            </h1>
            <span className="rounded bg-gray-800 px-2 py-0.5 font-mono text-sm text-gray-400">
              {ticker}
            </span>
          </div>
          {stock && (
            <p className="mt-1 text-sm text-gray-400">
              {stock.market} {stock.sector ? `/ ${stock.sector}` : ""}
            </p>
          )}
        </div>
        {latestPrice && (
          <div className="text-right">
            <p className="text-3xl font-semibold tabular-nums">
              {latestPrice.close.toLocaleString("ko-KR")}
            </p>
            <p className="text-xs text-gray-500">
              {latestPrice.trade_date} 종가
            </p>
          </div>
        )}
      </div>

      {/* 차트 영역 */}
      <div className="rounded-lg border border-gray-800 bg-[#111111] p-6">
        <p className="text-sm font-medium text-gray-400 mb-4">가격 차트</p>
        <StockChart ticker={ticker} />
      </div>

      {/* 분석 리포트 */}
      {analysis ? (
        <div className="space-y-6">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-semibold">AI 분석 리포트</h2>
            <RecommendationBadge recommendation={analysis.recommendation} />
          </div>

          {/* 요약 */}
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
                  <span className="font-medium tabular-nums">
                    {analysis.target_price.toLocaleString("ko-KR")}
                  </span>
                </div>
              )}
              <div>
                <span className="text-gray-500">분석일</span>{" "}
                <span className="font-medium">{analysis.analysis_date}</span>
              </div>
            </div>
          </div>

          {/* Bull / Bear Case */}
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

          {/* Key Factors */}
          {analysis.key_factors.length > 0 && (
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
          <p className="mt-1 text-xs text-gray-500">분석 스케줄러가 실행되면 자동으로 생성됩니다.</p>
        </div>
      )}
    </div>
  );
}
