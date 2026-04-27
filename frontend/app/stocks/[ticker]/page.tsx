"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { fetchAPI, fetchAnalysisHistory, fetchNewsImpactSummary } from "@/lib/api";
import type {
  AnalysisHistoryItem,
  Stock,
  AnalysisReport,
  DailyPrice,
  TechnicalIndicators,
  NewsArticle,
  NewsImpactSummary,
  StockDetailResponse,
} from "@/lib/api";
import StockChartWrapper from "@/components/charts/StockChartWrapper";

function formatNumber(val: number | null | undefined, opts?: Intl.NumberFormatOptions): string {
  if (val == null) return "-";
  return val.toLocaleString("ko-KR", opts);
}

function formatChangePct(val: number | null | undefined): string {
  if (val == null) return "-";
  const sign = val >= 0 ? "+" : "";
  return `${sign}${val.toFixed(2)}%`;
}

function formatReturn(val: number | null | undefined): string {
  if (val == null) return "-";
  const pct = val * 100;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%`;
}

function dataStatusText(status: string | null | undefined): string {
  if (!status || status === "ok") return "관측 완료";
  if (status === "raw_price_fallback") return "원시 종가 기준";
  if (status === "benchmark_missing") return "벤치마크 없음";
  if (status === "price_missing") return "가격 없음";
  if (status === "insufficient_window") return "관측 기간 부족";
  return status;
}

function observedWindowReturn(
  impact: NewsImpactSummary["recent_impacts"][number],
  windowLabel: string,
): number | null | undefined {
  return impact.observed_windows?.find((item) => item.window === windowLabel)?.abnormal_return;
}

function changePctColor(val: number | null | undefined): string {
  if (val == null) return "text-gray-500";
  if (val > 0) return "text-green-500";
  if (val < 0) return "text-red-500";
  return "text-gray-400";
}

function relativeTime(dateStr: string | null | undefined): string {
  if (!dateStr) return "-";
  try {
    const now = Date.now();
    const then = new Date(dateStr).getTime();
    if (isNaN(then)) return dateStr;
    const diffMs = now - then;
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return "방금 전";
    if (diffMin < 60) return `${diffMin}분 전`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}시간 전`;
    const diffDay = Math.floor(diffHr / 24);
    if (diffDay < 30) return `${diffDay}일 전`;
    return dateStr.slice(0, 10);
  } catch {
    return dateStr;
  }
}

function sentimentDotColor(label: string | null | undefined): string {
  if (!label) return "bg-gray-400";
  const lower = label.toLowerCase();
  if (lower === "positive") return "bg-emerald-400";
  if (lower === "negative") return "bg-rose-400";
  return "bg-gray-400";
}

function getRecommendationLabel(recommendation: string | null | undefined): string {
  if (!recommendation) return "-";

  const lower = recommendation.toLowerCase();
  if (lower.includes("strong_buy")) return "강력 매수";
  if (lower.includes("buy")) return "매수";
  if (lower.includes("strong_sell")) return "강력 매도";
  if (lower.includes("sell")) return "매도";
  if (lower.includes("hold")) return "보유";
  return recommendation;
}

function formatConfidence(value: number | null | undefined): string {
  if (value == null) return "-";
  return `${(value * 100).toFixed(0)}%`;
}

function formatSignedDelta(
  value: number | null,
  formatter: (delta: number) => string,
): string {
  if (value == null) return "비교 데이터 없음";
  if (value === 0) return "변화 없음";
  return formatter(value);
}

function getReportTypeLabel(analysisType: string | undefined): string {
  if (analysisType === "daily") return "최종 일일 리포트";
  return analysisType ?? "분석 리포트";
}

function RecommendationBadge({ recommendation }: { recommendation: string | null | undefined }) {
  if (!recommendation) return null;
  const lower = recommendation.toLowerCase();
  let bgColor = "bg-gray-700";
  let textColor = "text-gray-300";
  const label = getRecommendationLabel(recommendation);

  if (lower.includes("strong_buy")) { bgColor = "bg-green-600"; textColor = "text-white"; }
  else if (lower.includes("buy")) { bgColor = "bg-green-500/15"; textColor = "text-green-400"; }
  else if (lower.includes("strong_sell")) { bgColor = "bg-red-600"; textColor = "text-white"; }
  else if (lower.includes("sell")) { bgColor = "bg-red-500/15"; textColor = "text-red-400"; }
  else if (lower.includes("hold")) { bgColor = "bg-yellow-500/15"; textColor = "text-yellow-400"; }

  return (
    <span className={`inline-flex items-center rounded-md px-2.5 py-1 text-xs font-semibold ${bgColor} ${textColor}`}>
      {label}
    </span>
  );
}

function getRsiColor(val: number | null | undefined): string {
  if (val == null) return "text-gray-400";
  if (val >= 70) return "text-red-400";
  if (val <= 30) return "text-green-400";
  return "text-white";
}

function getRsiLabel(val: number | null | undefined): string {
  if (val == null) return "";
  if (val >= 70) return "과매수";
  if (val <= 30) return "과매도";
  return "중립";
}

function getTrendBadge(trend: string | null | undefined) {
  if (!trend) return null;
  const lower = trend.toLowerCase();
  if (lower === "uptrend" || lower === "up") {
    return <span className="inline-flex items-center rounded-md bg-green-500/15 px-2 py-0.5 text-xs font-semibold text-green-400">상승 추세</span>;
  }
  if (lower === "downtrend" || lower === "down") {
    return <span className="inline-flex items-center rounded-md bg-red-500/15 px-2 py-0.5 text-xs font-semibold text-red-400">하락 추세</span>;
  }
  return <span className="inline-flex items-center rounded-md bg-yellow-500/15 px-2 py-0.5 text-xs font-semibold text-yellow-400">횡보</span>;
}

function getMacdSignal(macd: number | null | undefined, signal: number | null | undefined): { text: string; color: string } {
  if (macd == null || signal == null) return { text: "-", color: "text-gray-400" };
  if (macd > signal) return { text: "매수 신호", color: "text-green-400" };
  if (macd < signal) return { text: "매도 신호", color: "text-red-400" };
  return { text: "중립", color: "text-gray-400" };
}

function SkeletonBlock({ className }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg border border-gray-800 bg-gray-900 ${className ?? "h-28"}`} />;
}

function getNewestPrice(prices: DailyPrice[]): DailyPrice | null {
  if (prices.length === 0) {
    return null;
  }

  return prices.reduce((latest, current) => {
    if (current.trade_date > latest.trade_date) {
      return current;
    }
    return latest;
  });
}

export default function StockDetailPage() {
  const params = useParams();
  const ticker = params.ticker as string;

  const [stock, setStock] = useState<Stock | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisReport | null>(null);
  const [latestPrice, setLatestPrice] = useState<DailyPrice | null>(null);
  const [technical, setTechnical] = useState<TechnicalIndicators | null>(null);
  const [news, setNews] = useState<NewsArticle[]>([]);
  const [newsImpact, setNewsImpact] = useState<NewsImpactSummary | null>(null);
  const [history, setHistory] = useState<AnalysisHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [techLoading, setTechLoading] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(true);

  useEffect(() => {
    if (!ticker) return;

    fetchAPI<StockDetailResponse>(`/api/v1/stocks/${ticker}/detail`)
      .then((data) => {
        setStock(data?.stock ?? null);
        setAnalysis(data?.analysis ?? null);
        const prices = Array.isArray(data?.prices) ? data.prices : [];
        setLatestPrice(data?.latest_price ?? getNewestPrice(prices));
        setNews(Array.isArray(data?.news) ? data.news.slice(0, 10) : []);
      })
      .catch(() => {
        // detail API 실패 시 개별 API fallback
        Promise.all([
          fetchAPI<{ stocks: Stock[] }>(`/api/v1/stocks?limit=1&offset=0`)
            .then((r) => (Array.isArray(r?.stocks) ? r.stocks : []).find((s) => s.ticker === ticker) ?? null)
            .catch(() => null),
          fetchAPI<{ ticker: string; analysis: AnalysisReport | null }>(`/api/v1/stocks/${ticker}/analysis`)
            .then((r) => r?.analysis ?? null)
            .catch(() => null),
          fetchAPI<{ prices: DailyPrice[] }>(`/api/v1/stocks/${ticker}/prices?limit=1`)
            .then((r) => (Array.isArray(r?.prices) ? r.prices : [])[0] ?? null)
            .catch(() => null),
        ]).then(([s, a, p]) => {
          setStock(s);
          setAnalysis(a);
          setLatestPrice(p);
        });
      })
      .finally(() => {
        setLoading(false);
      });

    fetchAnalysisHistory(ticker)
      .then((data) => {
        setHistory(Array.isArray(data?.history) ? data.history : []);
      })
      .catch(() => {
        setHistory([]);
      })
      .finally(() => {
        setHistoryLoading(false);
      });

    // 기술적 지표 별도 호출
    fetchAPI<{ ticker: string; indicators: TechnicalIndicators }>(`/api/v1/stocks/${ticker}/technical`)
      .then((data) => {
        setTechnical(data?.indicators ?? null);
      })
      .catch(() => {
        setTechnical(null);
      })
      .finally(() => {
        setTechLoading(false);
      });

    // 뉴스 영향 요약 호출
    fetchNewsImpactSummary(ticker, 7)
      .then((data) => {
        setNewsImpact(data);
      })
      .catch(() => {
        setNewsImpact(null);
      });
  }, [ticker]);

  if (loading) {
    return (
      <div className="space-y-6">
        <SkeletonBlock className="h-20" />
        <SkeletonBlock className="h-[400px]" />
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <SkeletonBlock key={i} className="h-28" />
          ))}
        </div>
      </div>
    );
  }

  const changePct = latestPrice
    ? latestPrice.open > 0
      ? ((latestPrice.close - latestPrice.open) / latestPrice.open) * 100
      : null
    : null;

  const macdSignal = getMacdSignal(technical?.macd, technical?.macd_signal);
  const latestHistory = history.length > 0 ? history[0] : null;
  const previousHistory = history.length > 1 ? history[1] : null;
  const oldestHistory = history.length > 0 ? history[history.length - 1] : null;
  const confidenceTrend =
    latestHistory?.confidence != null && previousHistory?.confidence != null
      ? latestHistory.confidence - previousHistory.confidence
      : null;
  const targetPriceTrend =
    latestHistory?.target_price != null && oldestHistory?.target_price != null
      ? latestHistory.target_price - oldestHistory.target_price
      : null;
  const recommendationTrendLabel = latestHistory
    ? previousHistory
      ? `${getRecommendationLabel(previousHistory.recommendation)} → ${getRecommendationLabel(latestHistory.recommendation)}`
      : getRecommendationLabel(latestHistory.recommendation)
    : "-";
  const historyCoverage =
    latestHistory && oldestHistory
      ? `${oldestHistory.analysis_date} ~ ${latestHistory.analysis_date}`
      : null;

  return (
    <div className="space-y-8">
      {/* 헤더: 종목명 + 티커 + 현재가 + 전일비 + 거래량 */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">{stock?.name ?? ticker}</h1>
            <span className="rounded bg-gray-800 px-2 py-0.5 font-mono text-sm text-gray-400">{ticker}</span>
            {analysis?.recommendation && <RecommendationBadge recommendation={analysis.recommendation} />}
          </div>
          {stock && (
            <p className="mt-1 text-sm text-gray-400">{stock.market}{stock.sector ? ` / ${stock.sector}` : ""}</p>
          )}
        </div>
        <div className="text-right">
          {latestPrice ? (
            <>
              <p className="text-3xl font-semibold tabular-nums">
                {formatNumber(latestPrice.close)}
              </p>
              <div className="flex items-center justify-end gap-3 mt-1">
                <span className={`text-sm font-medium tabular-nums ${changePctColor(changePct)}`}>
                  {formatChangePct(changePct)}
                </span>
                <span className="text-xs text-gray-500">
                  거래량 {formatNumber(latestPrice.volume)}
                </span>
              </div>
              <p className="text-xs text-gray-500 mt-0.5">{latestPrice.trade_date} 종가</p>
            </>
          ) : (
            <p className="text-sm text-gray-500">가격 데이터 없음</p>
          )}
        </div>
      </div>

      {/* 차트 영역 */}
      <div className="rounded-lg border border-gray-800 bg-[#111111] p-6">
        <p className="text-sm font-medium text-gray-400 mb-4">가격 차트</p>
        <StockChartWrapper ticker={ticker} />
      </div>

      {/* 기술적 지표 카드 (2x3 그리드) */}
      <div>
        <h2 className="text-lg font-semibold mb-4">기술적 지표</h2>
        {techLoading ? (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <SkeletonBlock key={i} className="h-28" />
            ))}
          </div>
        ) : technical ? (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            {/* RSI */}
            <div className="rounded-lg border border-gray-800 bg-[#111111] p-4">
              <p className="text-xs font-medium text-gray-400 mb-2">RSI (14)</p>
              <div className="flex items-end gap-2">
                <span className={`text-2xl font-semibold tabular-nums ${getRsiColor(technical.rsi_14)}`}>
                  {technical.rsi_14 != null ? technical.rsi_14.toFixed(1) : "-"}
                </span>
                {technical.rsi_14 != null && (
                  <span className={`text-xs font-medium mb-1 ${getRsiColor(technical.rsi_14)}`}>
                    {getRsiLabel(technical.rsi_14)}
                  </span>
                )}
              </div>
              {/* RSI 게이지 바 */}
              {technical.rsi_14 != null && (
                <div className="mt-3 relative">
                  <div className="h-2 rounded-full bg-gray-700 overflow-hidden flex">
                    <div className="w-[30%] bg-green-500/30" />
                    <div className="w-[40%] bg-gray-600/30" />
                    <div className="w-[30%] bg-red-500/30" />
                  </div>
                  <div
                    className="absolute top-0 h-2 w-1 bg-white rounded"
                    style={{ left: `${Math.min(Math.max(technical.rsi_14, 0), 100)}%` }}
                  />
                  <div className="flex justify-between mt-1 text-[10px] text-gray-500">
                    <span>0</span>
                    <span>30</span>
                    <span>70</span>
                    <span>100</span>
                  </div>
                </div>
              )}
            </div>

            {/* MACD */}
            <div className="rounded-lg border border-gray-800 bg-[#111111] p-4">
              <p className="text-xs font-medium text-gray-400 mb-2">MACD</p>
              <div className="space-y-1.5">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">MACD</span>
                  <span className="tabular-nums text-white">
                    {technical.macd != null ? technical.macd.toFixed(2) : "-"}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Signal</span>
                  <span className="tabular-nums text-white">
                    {technical.macd_signal != null ? technical.macd_signal.toFixed(2) : "-"}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Hist</span>
                  <span className="tabular-nums text-white">
                    {technical.macd_hist != null ? technical.macd_hist.toFixed(2) : "-"}
                  </span>
                </div>
              </div>
              <p className={`mt-2 text-xs font-medium ${macdSignal.color}`}>
                {macdSignal.text}
              </p>
            </div>

            {/* 볼린저밴드 */}
            <div className="rounded-lg border border-gray-800 bg-[#111111] p-4">
              <p className="text-xs font-medium text-gray-400 mb-2">볼린저 밴드</p>
              <div className="space-y-1.5">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">상단</span>
                  <span className="tabular-nums text-white">
                    {formatNumber(technical.bb_upper, { maximumFractionDigits: 0 })}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">중단</span>
                  <span className="tabular-nums text-white">
                    {formatNumber(technical.bb_middle, { maximumFractionDigits: 0 })}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">하단</span>
                  <span className="tabular-nums text-white">
                    {formatNumber(technical.bb_lower, { maximumFractionDigits: 0 })}
                  </span>
                </div>
              </div>
              {technical.price_position && (
                <p className="mt-2 text-xs text-gray-400">
                  위치: <span className="text-white font-medium">{technical.price_position}</span>
                </p>
              )}
            </div>

            {/* SMA 이평선 */}
            <div className="rounded-lg border border-gray-800 bg-[#111111] p-4">
              <p className="text-xs font-medium text-gray-400 mb-2">이동평균선</p>
              <div className="space-y-1.5">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">SMA 5</span>
                  <span className="tabular-nums text-white">
                    {formatNumber(technical.sma_5, { maximumFractionDigits: 0 })}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">SMA 20</span>
                  <span className="tabular-nums text-white">
                    {formatNumber(technical.sma_20, { maximumFractionDigits: 0 })}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">SMA 60</span>
                  <span className="tabular-nums text-white">
                    {formatNumber(technical.sma_60, { maximumFractionDigits: 0 })}
                  </span>
                </div>
              </div>
            </div>

            {/* 추세 */}
            <div className="rounded-lg border border-gray-800 bg-[#111111] p-4">
              <p className="text-xs font-medium text-gray-400 mb-2">추세</p>
              <div className="mt-2">
                {getTrendBadge(technical.trend)}
              </div>
              {technical.price_position && (
                <p className="mt-3 text-xs text-gray-400">
                  가격 위치: <span className="text-white">{technical.price_position}</span>
                </p>
              )}
            </div>

            {/* ATR 변동성 */}
            <div className="rounded-lg border border-gray-800 bg-[#111111] p-4">
              <p className="text-xs font-medium text-gray-400 mb-2">ATR (14)</p>
              <p className="text-2xl font-semibold tabular-nums text-white">
                {technical.atr_14 != null ? formatNumber(technical.atr_14, { maximumFractionDigits: 0 }) : "-"}
              </p>
              <p className="mt-1 text-xs text-gray-500">일일 변동성 (평균 진폭)</p>
            </div>
          </div>
        ) : (
          <div className="rounded-lg border border-gray-800 bg-[#111111] p-6">
            <p className="text-sm text-gray-400">기술적 지표 데이터가 없습니다.</p>
            <p className="mt-1 text-xs text-gray-500">가격 데이터가 충분히 수집되면 자동으로 계산됩니다.</p>
          </div>
        )}
      </div>

      {/* 뉴스 영향 요약 */}
      {newsImpact && (
        <div>
          <h2 className="text-lg font-semibold mb-4">최근 뉴스 영향과 관측 반응</h2>
          <div className="rounded-lg border border-[#1f1f1f] bg-[#111111] p-4">
            <div className="grid grid-cols-3 gap-3 mb-4">
              <div className="text-center">
                <div className="text-2xl font-bold text-green-400">{newsImpact.bullish_count}</div>
                <div className="text-xs text-gray-500">긍정</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-red-400">{newsImpact.bearish_count}</div>
                <div className="text-xs text-gray-500">부정</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-gray-400">{newsImpact.neutral_count}</div>
                <div className="text-xs text-gray-500">중립</div>
              </div>
            </div>

            <div className="mb-4 text-center">
              <span className="text-xs text-gray-500">총 기사 수 </span>
              <span className="text-sm font-semibold tabular-nums text-white">
                {newsImpact.total_count}
              </span>
            </div>

            {newsImpact.total_count > 0 && newsImpact.avg_impact_score !== 0 && (
              <div className="mb-4 text-center">
                <span className="text-xs text-gray-500">평균 영향 점수 </span>
                <span className={`text-sm font-semibold tabular-nums ${
                  newsImpact.avg_impact_score > 0 ? "text-green-400" :
                  newsImpact.avg_impact_score < 0 ? "text-red-400" : "text-gray-400"
                }`}>
                  {newsImpact.avg_impact_score >= 0 ? "+" : ""}{newsImpact.avg_impact_score.toFixed(3)}
                </span>
              </div>
            )}

            {newsImpact.total_count === 0 ? (
              <div className="rounded-lg border border-[#1f1f1f] bg-black/10 p-4 text-center">
                <p className="text-sm text-gray-400">최근 7일간 분석된 뉴스 영향이 없습니다.</p>
              </div>
            ) : (
              newsImpact.recent_impacts.slice(0, 5).map((imp, idx) => (
                <div key={`${imp.title}-${idx}`} className="border-t border-[#1f1f1f] py-3">
                  <div className="flex items-start gap-2">
                    <span className={`mt-0.5 text-xs font-bold shrink-0 ${
                      imp.impact_direction === "bullish" ? "text-green-400" :
                      imp.impact_direction === "bearish" ? "text-red-400" : "text-gray-400"
                    }`}>
                      {imp.impact_direction === "bullish" ? "\u25B2" : imp.impact_direction === "bearish" ? "\u25BC" : "\u2013"}
                    </span>
                    <div className="min-w-0 flex-1">
                      {imp.url ? (
                        <a
                          href={imp.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="line-clamp-1 text-sm text-gray-300 transition-colors hover:text-green-400"
                        >
                          {imp.title}
                        </a>
                      ) : (
                        <p className="line-clamp-1 text-sm text-gray-300">{imp.title}</p>
                      )}
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-gray-500">
                        {imp.impact_score != null && (
                          <span className={`font-medium ${
                            imp.impact_direction === "bullish" ? "text-green-400" :
                            imp.impact_direction === "bearish" ? "text-red-400" : "text-gray-400"
                          }`}>
                            {imp.impact_score >= 0 ? "+" : ""}{imp.impact_score.toFixed(2)}
                          </span>
                        )}
                        {imp.published_at && <span>{relativeTime(imp.published_at)}</span>}
                        {imp.reason && <span className="truncate">{imp.reason}</span>}
                      </div>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* AI 분석 리포트 */}
      {analysis ? (
        <div className="space-y-6">
          <h2 className="text-lg font-semibold">AI 분석 리포트</h2>

          <div className="rounded-lg border border-gray-800 bg-[#111111] p-5">
            <p className="text-sm leading-relaxed text-gray-300">{analysis.summary}</p>
            <div className="mt-4 flex flex-wrap gap-4 text-sm">
              <div>
                <span className="text-gray-500">신뢰도</span>
                <div className="mt-1 flex items-center gap-2">
                  <div className="h-2 w-24 rounded-full bg-gray-700 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-green-500"
                      style={{ width: `${(analysis.confidence ?? 0) * 100}%` }}
                    />
                  </div>
                  <span className="font-medium tabular-nums">
                    {analysis.confidence != null ? `${(analysis.confidence * 100).toFixed(0)}%` : "-"}
                  </span>
                </div>
              </div>
              {analysis.target_price != null && (
                <div>
                  <span className="text-gray-500">목표가</span>{" "}
                  <span className="font-medium tabular-nums">{formatNumber(analysis.target_price)}</span>
                </div>
              )}
              <div>
                <span className="text-gray-500">분석일</span>{" "}
                <span className="font-medium">{analysis.analysis_date ?? "-"}</span>
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

          {Array.isArray(analysis.key_factors) && analysis.key_factors.length > 0 && (
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
          <p className="text-sm text-gray-400">최종 일일 리포트가 아직 없습니다.</p>
          <p className="mt-1 text-xs text-gray-500">장 마감 후 일일 리포트가 생성되면 여기에 표시됩니다.</p>
        </div>
      )}

      <div className="space-y-4">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold">최종 일일 리포트 히스토리</h2>
            <p className="mt-1 text-sm text-gray-400">
              내부 analyst shard와 on-demand를 제외한 사용자용 최종 일일 리포트만 시간순으로 보여줍니다.
            </p>
          </div>
          <p className="text-xs text-gray-500 tabular-nums">
            {historyCoverage ?? "기록 없음"}
            {history.length > 0 ? ` · ${history.length}건` : ""}
          </p>
        </div>

        {historyLoading ? (
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {[1, 2, 3, 4].map((item) => (
                <SkeletonBlock key={item} className="h-28" />
              ))}
            </div>
            <SkeletonBlock className="h-52" />
          </div>
        ) : history.length > 0 ? (
          <>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-lg border border-gray-800 bg-[#111111] p-4">
                <p className="text-xs font-medium text-gray-400">최신 추천</p>
                <div className="mt-3 flex items-center gap-3">
                  <RecommendationBadge recommendation={latestHistory?.recommendation} />
                  <span className="text-sm text-gray-500">{latestHistory?.analysis_date ?? "-"}</span>
                </div>
                <p className="mt-3 text-xs text-gray-500">가장 최근 최종 일일 리포트 기준</p>
              </div>

              <div className="rounded-lg border border-gray-800 bg-[#111111] p-4">
                <p className="text-xs font-medium text-gray-400">추천 변화</p>
                <p className="mt-3 text-lg font-semibold text-white">{recommendationTrendLabel}</p>
                <p className="mt-2 text-xs text-gray-500">
                  {previousHistory ? "직전 최종 리포트 대비" : "현재 비교 가능한 이전 기록이 없습니다."}
                </p>
              </div>

              <div className="rounded-lg border border-gray-800 bg-[#111111] p-4">
                <p className="text-xs font-medium text-gray-400">신뢰도 추세</p>
                <p className="mt-3 text-2xl font-semibold tabular-nums text-white">
                  {formatConfidence(latestHistory?.confidence)}
                </p>
                <p className="mt-2 text-xs text-gray-500">
                  {formatSignedDelta(confidenceTrend, (delta) => {
                    const sign = delta > 0 ? "+" : "";
                    return `${sign}${(delta * 100).toFixed(0)}%p 직전 대비`;
                  })}
                </p>
              </div>

              <div className="rounded-lg border border-gray-800 bg-[#111111] p-4">
                <p className="text-xs font-medium text-gray-400">목표가 추세</p>
                <p className="mt-3 text-2xl font-semibold tabular-nums text-white">
                  {formatNumber(latestHistory?.target_price, { maximumFractionDigits: 0 })}
                </p>
                <p className="mt-2 text-xs text-gray-500">
                  {formatSignedDelta(targetPriceTrend, (delta) => {
                    const sign = delta > 0 ? "+" : "";
                    return `${sign}${formatNumber(delta, { maximumFractionDigits: 0 })} 최초 기록 대비`;
                  })}
                </p>
              </div>
            </div>

            <div className="overflow-hidden rounded-lg border border-gray-800 bg-[#111111]">
              <div className="hidden grid-cols-[120px_130px_110px_140px_minmax(0,1fr)] gap-4 border-b border-gray-800 bg-[#0d0d0d] px-4 py-3 text-xs font-medium text-gray-400 md:grid">
                <span>일자</span>
                <span>추천</span>
                <span>신뢰도</span>
                <span>목표가</span>
                <span>리포트 유형 / 출처</span>
              </div>

              <div className="divide-y divide-gray-800/80">
                {history.map((report) => (
                  <div
                    key={`${report.analysis_date}-${report.analysis_type}-${report.created_at ?? "no-created-at"}`}
                    className="flex flex-col gap-3 px-4 py-4 md:grid md:grid-cols-[120px_130px_110px_140px_minmax(0,1fr)] md:items-center md:gap-4"
                  >
                    <div>
                      <p className="text-xs text-gray-500 md:hidden">일자</p>
                      <p className="text-sm font-medium text-white">{report.analysis_date}</p>
                    </div>

                    <div>
                      <p className="text-xs text-gray-500 md:hidden">추천</p>
                      <RecommendationBadge recommendation={report.recommendation} />
                    </div>

                    <div>
                      <p className="text-xs text-gray-500 md:hidden">신뢰도</p>
                      <p className="text-sm font-medium tabular-nums text-white">
                        {formatConfidence(report.confidence)}
                      </p>
                    </div>

                    <div>
                      <p className="text-xs text-gray-500 md:hidden">목표가</p>
                      <p className="text-sm font-medium tabular-nums text-white">
                        {formatNumber(report.target_price, { maximumFractionDigits: 0 })}
                      </p>
                    </div>

                    <div className="min-w-0">
                      <p className="text-xs text-gray-500 md:hidden">리포트 유형 / 출처</p>
                      <p className="text-sm text-white">{getReportTypeLabel(report.analysis_type)}</p>
                      <p className="mt-1 text-xs text-gray-500">
                        {report.model_used ?? "모델 정보 없음"}
                        {report.created_at ? ` · 생성 ${report.created_at}` : ""}
                      </p>
                      <p className="mt-2 line-clamp-2 text-sm text-gray-400">{report.summary}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </>
        ) : (
          <div className="rounded-lg border border-gray-800 bg-[#111111] p-6">
            <p className="text-sm text-gray-400">최종 일일 리포트 히스토리가 아직 없습니다.</p>
            <p className="mt-1 text-xs text-gray-500">
              온디맨드 분석이나 내부 analyst shard는 이 타임라인에 섞지 않습니다.
            </p>
          </div>
        )}
      </div>

      {/* 관련 뉴스 */}
      <div>
        <h2 className="text-lg font-semibold mb-4">관련 뉴스</h2>
        {news.length > 0 ? (
          <div className="space-y-2">
            {news.map((article, idx) => (
              <div
                key={idx}
                className="rounded-lg border border-gray-800 bg-[#111111] p-4 hover:border-gray-700 transition-colors"
              >
                <div className="flex items-start gap-3">
                  <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${sentimentDotColor(article.sentiment_label)}`} />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-white truncate">
                      {article.url ? (
                        <a
                          href={article.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="hover:text-green-400 transition-colors"
                        >
                          {article.title ?? "제목 없음"}
                        </a>
                      ) : (
                        article.title ?? "제목 없음"
                      )}
                    </p>
                    {article.impact_summary && (
                      <p className="text-xs text-gray-400 mt-1 line-clamp-1">{article.impact_summary}</p>
                    )}
                    <div className="mt-1 flex items-center gap-2 text-xs text-gray-500">
                      <span className="font-medium text-gray-400">{article.source ?? "-"}</span>
                      <span>|</span>
                      <span>{relativeTime(article.published_at)}</span>
                      {article.sentiment_score != null && (
                        <>
                          <span>|</span>
                          <span className={`font-medium ${
                            article.sentiment_score > 0 ? "text-emerald-400" :
                            article.sentiment_score < 0 ? "text-rose-400" : "text-gray-400"
                          }`}>
                            {article.sentiment_score >= 0 ? "+" : ""}{article.sentiment_score.toFixed(2)}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-lg border border-gray-800 bg-[#111111] p-6">
            <p className="text-sm text-gray-400">관련 뉴스가 없습니다.</p>
          </div>
        )}
      </div>

      <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-4 text-xs leading-relaxed text-amber-100">
        이 화면의 뉴스 영향은 일봉 기준 시장 대비 관측 반응이며 인과관계나 투자 자문을 의미하지 않습니다.
        pykrx, FinanceDataReader, yfinance 등 무료/비공식 경로의 데이터는 지연되거나 제공처와 차이가 날 수 있습니다.
      </div>
    </div>
  );
}
