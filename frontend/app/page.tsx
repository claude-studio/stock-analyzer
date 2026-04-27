"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchAPI } from "@/lib/api";
import type { WatchlistItem, NewsArticle } from "@/lib/api";

interface MarketData {
  kospi: { close: number; change_pct: number } | null;
  kosdaq: { close: number; change_pct: number } | null;
}

interface HealthData {
  status: string;
  checks: Record<string, string>;
  jobs: { id: string; next_run: string }[];
}

function formatNumber(val: number | null | undefined, opts?: Intl.NumberFormatOptions): string {
  if (val == null) return "-";
  return val.toLocaleString("ko-KR", opts);
}

function formatChangePct(val: number | null | undefined): string {
  if (val == null) return "-";
  const sign = val >= 0 ? "+" : "";
  return `${sign}${val.toFixed(2)}%`;
}

function changePctColor(val: number | null | undefined): string {
  if (val == null) return "text-gray-500";
  if (val > 0) return "text-green-500";
  if (val < 0) return "text-red-500";
  return "text-gray-400";
}

function sentimentDot(label: string | null | undefined): string {
  if (!label) return "bg-gray-400";
  const lower = label.toLowerCase();
  if (lower === "positive") return "bg-emerald-400";
  if (lower === "negative") return "bg-rose-400";
  return "bg-gray-400";
}

function recommendationBadge(rec: string | null | undefined) {
  if (!rec) return null;
  const lower = rec.toLowerCase();
  let bg = "bg-gray-700";
  let text = "text-gray-300";
  let label = rec;

  if (lower.includes("strong_buy")) { bg = "bg-green-600"; text = "text-white"; label = "강력 매수"; }
  else if (lower.includes("buy")) { bg = "bg-green-500/15"; text = "text-green-400"; label = "매수"; }
  else if (lower.includes("strong_sell")) { bg = "bg-red-600"; text = "text-white"; label = "강력 매도"; }
  else if (lower.includes("sell")) { bg = "bg-red-500/15"; text = "text-red-400"; label = "매도"; }
  else if (lower.includes("hold")) { bg = "bg-yellow-500/15"; text = "text-yellow-400"; label = "보유"; }

  return (
    <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold ${bg} ${text}`}>
      {label}
    </span>
  );
}

function relativeTime(dateStr: string | null | undefined): string {
  if (!dateStr) return "-";
  try {
    const now = Date.now();
    const then = new Date(dateStr).getTime();
    const diffMs = now - then;
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return "방금 전";
    if (diffMin < 60) return `${diffMin}분 전`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}시간 전`;
    const diffDay = Math.floor(diffHr / 24);
    return `${diffDay}일 전`;
  } catch {
    return dateStr;
  }
}

function SkeletonCard() {
  return <div className="h-28 animate-pulse rounded-lg border border-gray-800 bg-gray-900" />;
}

function SkeletonRow() {
  return <div className="h-12 animate-pulse rounded bg-gray-800/30" />;
}

export default function DashboardPage() {
  const [market, setMarket] = useState<MarketData | null>(null);
  const [health, setHealth] = useState<HealthData | null>(null);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [news, setNews] = useState<NewsArticle[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetchAPI<MarketData>("/api/v1/market/overview").catch(() => null),
      fetchAPI<HealthData>("/health").catch(() => null),
      fetchAPI<{ watchlist: WatchlistItem[] }>("/api/v1/watchlist").catch(() => null),
      fetchAPI<{ news: NewsArticle[] }>("/api/v1/news?limit=5").catch(() => null),
    ]).then(([m, h, w, n]) => {
      setMarket(m);
      setHealth(h);
      setWatchlist(Array.isArray(w?.watchlist) ? w.watchlist : []);
      setNews(Array.isArray(n?.news) ? n.news : []);
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
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <SkeletonCard />
          <SkeletonCard />
        </div>
        <div className="space-y-3">
          {[1, 2, 3, 4, 5].map((i) => (
            <SkeletonRow key={i} />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* 헤더 */}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">대시보드</h1>
        <p className="mt-1 text-sm text-gray-400">KRX 시장 개요 / 관심 종목 / 뉴스</p>
        <p className="mt-2 text-xs text-gray-500">미국 종목은 종목 목록·상세 화면에서만 제한 지원됩니다.</p>
      </div>

      {/* 상단: KOSPI / KOSDAQ 지수 카드 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="rounded-lg border border-gray-800 bg-[#111111] p-5">
          <p className="text-sm font-medium text-gray-400">KOSPI</p>
          {market?.kospi?.close != null ? (
            <div className="mt-2">
              <p className="text-2xl font-semibold tabular-nums">
                {formatNumber(market.kospi.close, { minimumFractionDigits: 2 })}
              </p>
              <span className={`text-sm font-medium tabular-nums ${changePctColor(market.kospi.change_pct)}`}>
                {formatChangePct(market.kospi.change_pct)}
              </span>
            </div>
          ) : (
            <p className="mt-2 text-sm text-gray-500">데이터 없음</p>
          )}
        </div>

        <div className="rounded-lg border border-gray-800 bg-[#111111] p-5">
          <p className="text-sm font-medium text-gray-400">KOSDAQ</p>
          {market?.kosdaq?.close != null ? (
            <div className="mt-2">
              <p className="text-2xl font-semibold tabular-nums">
                {formatNumber(market.kosdaq.close, { minimumFractionDigits: 2 })}
              </p>
              <span className={`text-sm font-medium tabular-nums ${changePctColor(market.kosdaq.change_pct)}`}>
                {formatChangePct(market.kosdaq.change_pct)}
              </span>
            </div>
          ) : (
            <p className="mt-2 text-sm text-gray-500">데이터 없음</p>
          )}
        </div>
      </div>

      {/* 중단: 관심 종목 워치리스트 */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-lg font-semibold">관심 종목</h2>
            <p className="mt-1 text-xs text-gray-500">대시보드 요약은 현재 KRX 관심 종목 기준입니다.</p>
          </div>
          <Link href="/stocks" className="text-sm text-gray-400 hover:text-white transition-colors">
            전체 보기 &rarr;
          </Link>
        </div>

        {watchlist.length > 0 ? (
          <div className="overflow-x-auto rounded-lg border border-gray-800">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 bg-[#0d0d0d]">
                  <th className="px-4 py-3 text-left font-medium text-gray-400">티커</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-400">종목명</th>
                  <th className="px-4 py-3 text-right font-medium text-gray-400">현재가</th>
                  <th className="px-4 py-3 text-right font-medium text-gray-400">전일비</th>
                  <th className="px-4 py-3 text-right font-medium text-gray-400">거래량</th>
                  <th className="px-4 py-3 text-center font-medium text-gray-400">AI 추천</th>
                </tr>
              </thead>
              <tbody>
                {watchlist.map((item) => (
                  <tr
                    key={item.ticker}
                    className="border-b border-gray-800/50 transition-colors hover:bg-gray-800/30 cursor-pointer"
                    onClick={() => { window.location.href = `/stocks/${item.ticker}`; }}
                  >
                    <td className="px-4 py-3 font-mono text-sm font-medium text-green-500">
                      {item.ticker}
                    </td>
                    <td className="px-4 py-3 font-medium text-white">{item.name ?? "-"}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-white">
                      {formatNumber(item.close)}
                    </td>
                    <td className={`px-4 py-3 text-right tabular-nums font-medium ${changePctColor(item.change_pct)}`}>
                      {formatChangePct(item.change_pct)}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-gray-400">
                      {formatNumber(item.volume)}
                    </td>
                    <td className="px-4 py-3 text-center">
                      {recommendationBadge(item.recommendation)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="rounded-lg border border-gray-800 bg-[#111111] p-6 text-center">
            <p className="text-sm text-gray-400">KRX 관심 종목이 없습니다.</p>
            <p className="mt-1 text-xs text-gray-500">종목 목록에서 관심 종목을 등록하세요. 미국 종목은 제한 지원됩니다.</p>
          </div>
        )}
      </div>

      {/* 하단: 뉴스 + 시스템 상태 */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* 하단 좌: 최근 뉴스 피드 */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">최근 뉴스</h2>
            <Link href="/news" className="text-sm text-gray-400 hover:text-white transition-colors">
              전체 보기 &rarr;
            </Link>
          </div>

          {news.length > 0 ? (
            <div className="space-y-2">
              {news.map((article, idx) => (
                <div
                  key={idx}
                  className="rounded-lg border border-gray-800 bg-[#111111] p-4 hover:border-gray-700 transition-colors"
                >
                  <div className="flex items-start gap-3">
                    <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${sentimentDot(article.sentiment_label)}`} />
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
                      <div className="mt-1 flex items-center gap-2 text-xs text-gray-500">
                        <span className="font-medium text-gray-400">{article.source ?? "-"}</span>
                        <span>|</span>
                        <span>{relativeTime(article.published_at)}</span>
                        {article.stock_ticker && (
                          <>
                            <span>|</span>
                            <Link
                              href={`/stocks/${article.stock_ticker}`}
                              className="text-green-500 hover:text-green-400"
                              onClick={(e) => e.stopPropagation()}
                            >
                              {article.stock_name ?? article.stock_ticker}
                            </Link>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-lg border border-gray-800 bg-[#111111] p-6 text-center">
              <p className="text-sm text-gray-400">뉴스 데이터가 없습니다.</p>
              <p className="mt-1 text-xs text-gray-500">뉴스 수집 스케줄러가 실행되면 표시됩니다.</p>
            </div>
          )}
        </div>

        {/* 하단 우: 시스템 상태 + 스케줄 */}
        <div>
          <h2 className="text-lg font-semibold mb-4">시스템 상태</h2>
          <div className="rounded-lg border border-gray-800 bg-[#111111] p-5">
            {health ? (
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <span className={`inline-block h-2.5 w-2.5 rounded-full ${health.status === "ok" ? "bg-green-500" : "bg-yellow-500"}`} />
                  <span className="text-sm font-medium">
                    {health.status === "ok" ? "정상 운영 중" : health.status}
                  </span>
                </div>

                {Array.isArray(health.jobs) && health.jobs.length > 0 ? (
                  <div>
                    <p className="text-xs font-medium text-gray-400 mb-2">스케줄 ({health.jobs.length}개)</p>
                    <div className="space-y-1.5">
                      {health.jobs.map((job) => (
                        <div key={job.id} className="flex items-center justify-between text-xs">
                          <span className="font-mono text-gray-300">{job.id}</span>
                          <span className="tabular-nums text-gray-500">{job.next_run}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-gray-500">등록된 스케줄이 없습니다.</p>
                )}
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <span className="inline-block h-2.5 w-2.5 rounded-full bg-red-500" />
                <span className="text-sm text-gray-500">API 서버 연결 실패</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
