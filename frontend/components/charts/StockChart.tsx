"use client";

import { useEffect, useState } from "react";
import { fetchAPI } from "@/lib/api";
import type { DailyPrice } from "@/lib/api";
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

export default function StockChart({ ticker }: StockChartProps) {
  const [candleData, setCandleData] = useState<CandlestickData[]>([]);
  const [volumeData, setVolumeData] = useState<VolumeData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);

      try {
        const prices = await fetchAPI<DailyPrice[]>(
          `/api/v1/stocks/${ticker}/prices?limit=120`,
        );

        if (cancelled) return;

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
      } catch (err) {
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
  }, [ticker]);

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

  return (
    <div className="space-y-1">
      <CandlestickChart data={candleData} />
      <VolumeChart data={volumeData} />
    </div>
  );
}
