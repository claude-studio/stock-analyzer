"use client";

import dynamic from "next/dynamic";

const StockChart = dynamic(
  () => import("@/components/charts/StockChart"),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-[400px] items-center justify-center">
        <p className="text-sm text-gray-500">차트 로딩 중...</p>
      </div>
    ),
  },
);

export default function StockChartWrapper({ ticker }: { ticker: string }) {
  return <StockChart ticker={ticker} />;
}
