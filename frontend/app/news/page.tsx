"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchAPI } from "@/lib/api";
import type { NewsArticle } from "@/lib/api";

const SOURCE_COLORS: Record<string, string> = {
  "연합인포맥스": "bg-blue-500/15 text-blue-400 border-blue-500/30",
  "한국경제": "bg-purple-500/15 text-purple-400 border-purple-500/30",
  "매일경제": "bg-orange-500/15 text-orange-400 border-orange-500/30",
  "이데일리": "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
};

function getSourceColor(source: string | null | undefined): string {
  if (!source) return "bg-gray-700/50 text-gray-400 border-gray-600/30";
  return SOURCE_COLORS[source] ?? "bg-gray-700/50 text-gray-400 border-gray-600/30";
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

function sentimentColor(label: string | null | undefined): string {
  if (!label) return "text-gray-400";
  const lower = label.toLowerCase();
  if (lower === "positive") return "text-emerald-400";
  if (lower === "negative") return "text-rose-400";
  return "text-gray-400";
}

function sentimentDotColor(label: string | null | undefined): string {
  if (!label) return "bg-gray-400";
  const lower = label.toLowerCase();
  if (lower === "positive") return "bg-emerald-400";
  if (lower === "negative") return "bg-rose-400";
  return "bg-gray-400";
}

function sentimentLabel(label: string | null | undefined): string {
  if (!label) return "중립";
  const lower = label.toLowerCase();
  if (lower === "positive") return "긍정";
  if (lower === "negative") return "부정";
  return "중립";
}

type SentimentFilter = "all" | "positive" | "negative" | "neutral";

function SkeletonCard() {
  return (
    <div className="h-24 animate-pulse rounded-lg border border-gray-800 bg-gray-900" />
  );
}

export default function NewsPage() {
  const [articles, setArticles] = useState<NewsArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sentimentFilter, setSentimentFilter] = useState<SentimentFilter>("all");
  const [sourceFilter, setSourceFilter] = useState<string>("all");

  useEffect(() => {
    fetchAPI<{ news: NewsArticle[] }>("/api/v1/news?limit=100")
      .then((data) => {
        setArticles(Array.isArray(data?.news) ? data.news : []);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "뉴스 로딩 실패");
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  const sources = Array.from(
    new Set(articles.map((a) => a.source).filter(Boolean))
  ).sort();

  const filtered = articles.filter((a) => {
    if (sentimentFilter !== "all") {
      const label = (a.sentiment_label ?? "neutral").toLowerCase();
      if (sentimentFilter === "positive" && label !== "positive") return false;
      if (sentimentFilter === "negative" && label !== "negative") return false;
      if (sentimentFilter === "neutral" && label !== "neutral" && label !== "") return false;
    }
    if (sourceFilter !== "all" && a.source !== sourceFilter) return false;
    return true;
  });

  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">뉴스 피드</h1>
        <p className="mt-1 text-sm text-gray-400">AI 감성 분석이 적용된 실시간 금융 뉴스</p>
      </div>

      {/* 필터 */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="flex gap-2">
          {(
            [
              { key: "all", label: "전체" },
              { key: "positive", label: "긍정" },
              { key: "negative", label: "부정" },
              { key: "neutral", label: "중립" },
            ] as { key: SentimentFilter; label: string }[]
          ).map((f) => (
            <button
              key={f.key}
              onClick={() => setSentimentFilter(f.key)}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                sentimentFilter === f.key
                  ? "bg-gray-700 text-white"
                  : "text-gray-400 hover:bg-gray-800/50 hover:text-white"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        <select
          value={sourceFilter}
          onChange={(e) => setSourceFilter(e.target.value)}
          className="rounded-lg border border-gray-800 bg-[#111111] px-4 py-2 text-sm text-white outline-none focus:border-gray-600 transition-colors"
        >
          <option value="all">전체 소스</option>
          {sources.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </div>

      {/* 뉴스 카드 리스트 */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3, 4, 5].map((i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : error ? (
        <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-6">
          <p className="text-sm text-red-400">뉴스를 불러올 수 없습니다: {error}</p>
          <p className="mt-1 text-xs text-gray-500">API 서버 연결을 확인하세요.</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-lg border border-gray-800 bg-[#111111] p-6 text-center">
          <p className="text-sm text-gray-400">
            {articles.length === 0 ? "수집된 뉴스가 없습니다." : "필터 조건에 맞는 뉴스가 없습니다."}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((article, idx) => (
            <div
              key={idx}
              className="rounded-lg border border-gray-800 bg-[#111111] p-5 hover:border-gray-700 transition-colors"
            >
              <div className="flex items-start gap-4">
                {/* 감성 dot */}
                <span className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${sentimentDotColor(article.sentiment_label)}`} />

                <div className="min-w-0 flex-1">
                  {/* 제목 */}
                  <h3 className="text-sm font-medium text-white leading-relaxed">
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
                  </h3>

                  {/* 메타 정보 */}
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    {/* 소스 배지 */}
                    <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${getSourceColor(article.source)}`}>
                      {article.source ?? "기타"}
                    </span>

                    <span className="text-xs text-gray-500">{relativeTime(article.published_at)}</span>

                    {/* 감성 라벨 */}
                    <span className={`text-xs font-medium ${sentimentColor(article.sentiment_label)}`}>
                      {sentimentLabel(article.sentiment_label)}
                    </span>

                    {/* 감성 점수 바 */}
                    {article.sentiment_score != null && (
                      <div className="flex items-center gap-1.5">
                        <div className="h-1.5 w-16 rounded-full bg-gray-700 overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              article.sentiment_score >= 0 ? "bg-emerald-400" : "bg-rose-400"
                            }`}
                            style={{
                              width: `${Math.abs(article.sentiment_score) * 50 + 50}%`,
                              marginLeft: article.sentiment_score < 0 ? "0" : "50%",
                              transform: article.sentiment_score < 0 ? "none" : "none",
                            }}
                          />
                        </div>
                        <span className="text-xs tabular-nums text-gray-500">
                          {article.sentiment_score >= 0 ? "+" : ""}{article.sentiment_score.toFixed(2)}
                        </span>
                      </div>
                    )}

                    {/* 연결된 종목 태그 */}
                    {article.stock_ticker && (
                      <Link
                        href={`/stocks/${article.stock_ticker}`}
                        className="inline-flex items-center rounded-md bg-green-500/10 border border-green-500/20 px-2 py-0.5 text-xs font-medium text-green-400 hover:bg-green-500/20 transition-colors"
                      >
                        {article.stock_name ?? article.stock_ticker}
                      </Link>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <p className="text-xs text-gray-500 tabular-nums">
        {filtered.length}건 표시 / 전체 {articles.length}건
      </p>
    </div>
  );
}
