"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchAPI } from "@/lib/api";
import type { Stock } from "@/lib/api";

export default function StocksPage() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [marketFilter, setMarketFilter] = useState("all");

  useEffect(() => {
    async function load() {
      try {
        const data = await fetchAPI<{ stocks?: Stock[] }>("/api/v1/stocks");
        setStocks(Array.isArray(data) ? data : data.stocks ?? []);
      } catch (err) {
        setError(err instanceof Error ? err.message : "데이터 로딩 실패");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const markets = Array.from(new Set(stocks.map((s) => s.market))).sort();

  const filtered = stocks.filter((s) => {
    const matchSearch =
      s.ticker.toLowerCase().includes(search.toLowerCase()) ||
      s.name.toLowerCase().includes(search.toLowerCase());
    const matchMarket = marketFilter === "all" || s.market === marketFilter;
    return matchSearch && matchMarket;
  });

  return (
    <div className="min-w-0 space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">종목 목록</h1>
        <p className="mt-1 text-sm text-gray-400">등록된 종목 현황</p>
        <p className="mt-2 text-xs text-gray-500">KRX 중심으로 운영되며 미국 종목은 설정된 watchlist 심볼만 제한 지원됩니다.</p>
      </div>

      {/* 검색 / 필터 */}
      <div className="flex flex-col gap-3 sm:flex-row">
        <input
          type="text"
          placeholder="종목명 또는 티커 검색..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 rounded-lg border border-gray-800 bg-[#111111] px-4 py-2.5 text-sm text-white placeholder-gray-500 outline-none focus:border-gray-600 transition-colors"
        />
        <select
          value={marketFilter}
          onChange={(e) => setMarketFilter(e.target.value)}
          className="rounded-lg border border-gray-800 bg-[#111111] px-4 py-2.5 text-sm text-white outline-none focus:border-gray-600 transition-colors"
        >
          <option value="all">전체 시장</option>
          {markets.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </div>

      {/* 테이블 */}
      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-12 rounded-lg bg-gray-800/30 animate-pulse" />
          ))}
        </div>
      ) : error ? (
        <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-6">
          <p className="text-sm text-red-400">데이터를 불러올 수 없습니다: {error}</p>
          <p className="mt-1 text-xs text-gray-500">API 서버가 실행 중인지 확인하세요.</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-lg border border-gray-800 bg-[#111111] p-6 text-center">
          <p className="text-sm text-gray-400">
            {stocks.length === 0 ? "등록된 종목이 없습니다" : "검색 결과가 없습니다"}
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 bg-[#0d0d0d]">
                <th className="px-4 py-3 text-left font-medium text-gray-400">티커</th>
                <th className="px-4 py-3 text-left font-medium text-gray-400">종목명</th>
                <th className="px-4 py-3 text-left font-medium text-gray-400">시장</th>
                <th className="px-4 py-3 text-left font-medium text-gray-400">섹터</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((stock) => (
                <tr
                  key={stock.ticker}
                  className="border-b border-gray-800/50 transition-colors hover:bg-gray-800/30"
                >
                  <td className="px-4 py-3">
                    <Link
                      href={`/stocks/${stock.ticker}`}
                      className="font-mono text-sm font-medium text-green-500 hover:text-green-400 transition-colors"
                    >
                      {stock.ticker}
                    </Link>
                  </td>
                  <td className="px-4 py-3 font-medium text-white">
                    <Link
                      href={`/stocks/${stock.ticker}`}
                      className="hover:text-green-400 transition-colors"
                    >
                      {stock.name}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-gray-400">{stock.market}</td>
                  <td className="px-4 py-3 text-gray-400">{stock.sector ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-xs text-gray-500 tabular-nums">
        미국 종목 가격은 USD 종가 기준으로 제한 제공됩니다.
      </p>
      <p className="text-xs text-gray-500 tabular-nums">
        총 {filtered.length}개 / 전체 {stocks.length}개
      </p>
    </div>
  );
}
