"use client";

import { useEffect, useState } from "react";
import { fetchAPI } from "@/lib/api";
import type { DailyPrice, NewsImpact, NewsImpactSummary } from "@/lib/api";
import type { SeriesMarker } from "lightweight-charts";
import CandlestickChart from "./CandlestickChart";
import VolumeChart from "./VolumeChart";

interface StockChartProps {
  ticker: string;
}

interface CandlestickData {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

interface VolumeData {
  time: string;
  value: number;
  color: string;
}

const RANGE_OPTIONS = [
  { label: "1M", limit: 22 },
  { label: "3M", limit: 66 },
  { label: "6M", limit: 132 },
  { label: "1Y", limit: 252 },
] as const;

function formatReturn(value: number | null | undefined): string {
  if (value == null) return "-";
  const pct = value * 100;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%`;
}

function statusLabel(status: string | null | undefined): string {
  if (!status || status === "ok") return "관측 완료";
  if (status === "raw_price_fallback") return "원시 종가 기준";
  if (status === "benchmark_missing") return "벤치마크 없음";
  if (status === "price_missing") return "가격 없음";
  if (status === "insufficient_window") return "관측 기간 부족";
  return status;
}

function getWindowReturn(
  event: NewsImpact,
  windowLabel: string,
): number | null | undefined {
  return event.observed_windows?.find((item) => item.window === windowLabel)?.abnormal_return;
}

export default function StockChart({ ticker }: StockChartProps) {
  const [candleData, setCandleData] = useState<CandlestickData[]>([]);
  const [volumeData, setVolumeData] = useState<VolumeData[]>([]);
  const [events, setEvents] = useState<NewsImpact[]>([]);
  const [range, setRange] = useState<(typeof RANGE_OPTIONS)[number]>(RANGE_OPTIONS[1]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);

      try {
        const [priceRes, impactRes] = await Promise.all([
          fetchAPI<{ prices: DailyPrice[] } | DailyPrice[]>(
            `/api/v1/stocks/${ticker}/prices?limit=${range.limit}`,
          ),
          fetchAPI<NewsImpactSummary>(
            `/api/v1/stocks/${ticker}/news-impact?days=90`,
          ).catch(() => null),
        ]);

        if (cancelled) return;

        const prices = Array.isArray(priceRes) ? priceRes : priceRes.prices ?? [];
        const sorted = [...prices].sort(
          (a, b) => a.trade_date.localeCompare(b.trade_date),
        );

        const candles: CandlestickData[] = sorted.map((p) => ({
          time: p.trade_date,
          open: p.open,
          high: p.high,
          low: p.low,
          close: p.close,
        }));

        const volumes: VolumeData[] = sorted.map((p) => ({
          time: p.trade_date,
          value: p.volume,
          color: p.close >= p.open ? "#22c55e80" : "#ef444480",
        }));

        setCandleData(candles);
        setVolumeData(volumes);
        setEvents(impactRes?.event_markers ?? impactRes?.recent_impacts ?? []);
      } catch {
        if (!cancelled) {
          setError("차트 데이터를 불러올 수 없습니다");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [ticker, range]);

  if (loading) {
    return (
      <div className="space-y-2">
        <div className="h-[400px] animate-pulse rounded-lg bg-gray-800" />
        <div className="h-[100px] animate-pulse rounded-lg bg-gray-800" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-[400px] items-center justify-center rounded-lg border border-gray-800 bg-gray-900">
        <p className="text-sm text-gray-500">{error}</p>
      </div>
    );
  }

  const markers: SeriesMarker<string>[] = events
    .filter((event) => event.effective_trading_date)
    .map((event) => {
      const isBearish = event.impact_direction === "bearish" || (event.abnormal_return ?? 0) < 0;
      return {
        time: event.effective_trading_date ?? "",
        position: isBearish ? "aboveBar" : "belowBar",
        color: isBearish ? "#ef4444" : "#22c55e",
        shape: isBearish ? "arrowDown" : "arrowUp",
        text: event.marker_label ?? "뉴스",
      };
    });

  const latestDate = candleData.at(-1)?.time;
  const visibleEvents = events.slice(0, 5);

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap gap-2">
          {RANGE_OPTIONS.map((option) => (
            <button
              key={option.label}
              type="button"
              onClick={() => setRange(option)}
              className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
                option.label === range.label
                  ? "bg-green-500/20 text-green-300"
                  : "bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
        <div className="rounded-md border border-amber-500/20 bg-amber-500/10 px-3 py-1 text-xs text-amber-200">
          일봉 기준 · 참고용 데이터{latestDate ? ` · ${latestDate} 기준` : ""}
        </div>
      </div>

      <CandlestickChart data={candleData} markers={markers} />
      <VolumeChart data={volumeData} />

      <div className="rounded-lg border border-gray-800 bg-[#0d0d0d] p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-gray-300">뉴스 이벤트 관측 반응</p>
            <p className="mt-1 text-xs text-gray-500">
              마커는 뉴스의 예상 방향과 이후 일봉 기준 시장 대비 관측 반응을 함께 표시합니다.
            </p>
          </div>
          <span className="rounded bg-gray-800 px-2 py-1 text-xs text-gray-400">
            {events.length}건
          </span>
        </div>
        {visibleEvents.length > 0 ? (
          <div className="space-y-2">
            {visibleEvents.map((event) => (
              <div
                key={`${event.article_id ?? event.title}-${event.effective_trading_date}`}
                className="grid gap-2 rounded-md border border-gray-800 bg-black/20 p-3 text-xs sm:grid-cols-[1fr_auto]"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-gray-200 line-clamp-1">
                      {event.title ?? event.reason ?? "뉴스 이벤트"}
                    </span>
                    {event.confounded && (
                      <span className="rounded bg-yellow-500/15 px-1.5 py-0.5 text-yellow-300">복합 이벤트</span>
                    )}
                  </div>
                  <p className="mt-1 text-gray-500">
                    관측일 {event.effective_trading_date ?? "-"} · {event.benchmark ?? "benchmark"} 대비 · {statusLabel(event.data_status)}
                  </p>
                </div>
                <div className="flex items-center gap-4 text-right tabular-nums">
                  <div>
                    <p className="text-gray-500">종목</p>
                    <p className="text-gray-200">{formatReturn(event.stock_return)}</p>
                  </div>
                  <div>
                    <p className="text-gray-500">1D 초과</p>
                    <p className={(event.abnormal_return ?? 0) >= 0 ? "text-green-400" : "text-red-400"}>
                      {formatReturn(event.abnormal_return)}
                    </p>
                  </div>
                  <div>
                    <p className="text-gray-500">3D 초과</p>
                    <p className={(getWindowReturn(event, "0,+3D") ?? 0) >= 0 ? "text-green-400" : "text-red-400"}>
                      {formatReturn(getWindowReturn(event, "0,+3D"))}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-md border border-gray-800 bg-black/20 p-3 text-sm text-gray-500">
            아직 차트에 표시할 뉴스 영향 이벤트가 없습니다.
          </div>
        )}
      </div>
    </div>
  );
}
