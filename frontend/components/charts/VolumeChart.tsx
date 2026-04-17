"use client";

import { useEffect, useRef } from "react";
import { createChart, HistogramSeries } from "lightweight-charts";
import type { IChartApi } from "lightweight-charts";

interface VolumeChartProps {
  data: {
    time: string;
    value: number;
    color: string;
  }[];
  height?: number;
}

export default function VolumeChart({ data, height = 100 }: VolumeChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      height,
      autoSize: true,
      layout: {
        background: { color: "#0a0a0a" },
        textColor: "#9ca3af",
      },
      grid: {
        vertLines: { color: "#1f2937" },
        horzLines: { color: "#1f2937" },
      },
      timeScale: {
        borderColor: "#1f2937",
      },
      rightPriceScale: {
        borderColor: "#1f2937",
      },
    });

    const series = chart.addSeries(HistogramSeries);
    series.setData(data);
    chart.timeScale().fitContent();
    chartRef.current = chart;

    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [data, height]);

  return (
    <div
      ref={containerRef}
      style={{ width: "100%", height }}
    />
  );
}
