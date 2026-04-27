"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { fetchNewsDetail } from "@/lib/api";
import type { NewsArticle, NewsImpact } from "@/lib/api";

const CATEGORY_LABELS: Record<string, { label: string; color: string }> = {
  earnings: { label: "실적", color: "bg-blue-500/20 text-blue-400" },
  policy: { label: "정책", color: "bg-purple-500/20 text-purple-400" },
  macro: { label: "매크로", color: "bg-amber-500/20 text-amber-400" },
  sector: { label: "섹터", color: "bg-cyan-500/20 text-cyan-400" },
  supply_demand: { label: "수급", color: "bg-rose-500/20 text-rose-400" },
  rumor: { label: "루머", color: "bg-red-500/20 text-red-400" },
  general: { label: "일반", color: "bg-gray-500/20 text-gray-400" },
};

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "-";
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    return d.toLocaleDateString("ko-KR", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return dateStr;
  }
}

function sentimentLabelText(score: number | null | undefined): string {
  if (score == null) return "중립";
  if (score > 0.3) return "긍정";
  if (score < -0.3) return "부정";
  return "중립";
}

function formatReturn(value: number | null | undefined): string {
  if (value == null) return "-";
  const pct = value * 100;
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

function SkeletonBlock({ className }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-gray-800 ${className ?? "h-28"}`} />;
}

function ImpactCard({ impact }: { impact: NewsImpact }) {
  const borderColor =
    impact.impact_direction === "bullish"
      ? "border-green-500/40"
      : impact.impact_direction === "bearish"
        ? "border-red-500/40"
        : "border-gray-600/40";

  const icon =
    impact.impact_direction === "bullish"
      ? "\u25B2"
      : impact.impact_direction === "bearish"
        ? "\u25BC"
        : "\u2013";

  const iconColor =
    impact.impact_direction === "bullish"
      ? "text-green-400"
      : impact.impact_direction === "bearish"
        ? "text-red-400"
        : "text-gray-400";

  const scoreColor =
    impact.impact_direction === "bullish"
      ? "text-green-400"
      : impact.impact_direction === "bearish"
        ? "text-red-400"
        : "text-gray-400";

  return (
    <Link href={`/stocks/${impact.stock_ticker}`}>
      <div className={`rounded-lg border ${borderColor} bg-[#111111] p-4 hover:bg-[#161616] transition-colors cursor-pointer`}>
        <div className="flex items-center gap-2 mb-2">
          <span className={`text-lg font-bold ${iconColor}`}>{icon}</span>
          <span className="text-sm font-semibold text-white">{impact.stock_name}</span>
        </div>
        <p className={`text-xl font-bold tabular-nums ${scoreColor}`}>
          {impact.impact_score != null
            ? `${impact.impact_score >= 0 ? "+" : ""}${impact.impact_score.toFixed(2)}`
            : "0.00"}
        </p>
        {impact.reason && (
          <p className="text-xs text-gray-400 mt-2 line-clamp-2">{impact.reason}</p>
        )}
        <div className="mt-3 rounded-md border border-gray-800 bg-black/20 p-2 text-xs">
          <div className="flex items-center justify-between gap-2">
            <span className="text-gray-500">관측 반응</span>
            <span className={(impact.abnormal_return ?? 0) >= 0 ? "text-green-400" : "text-red-400"}>
              {formatReturn(impact.abnormal_return)}
            </span>
          </div>
          <div className="mt-1 flex items-center justify-between gap-2 text-gray-500">
            <span>{impact.effective_trading_date ?? "관측일 없음"}</span>
            <span>{dataStatusText(impact.data_status)}</span>
          </div>
          {impact.confounded && (
            <p className="mt-1 text-yellow-400">동일 세션 복합 이벤트</p>
          )}
        </div>
      </div>
    </Link>
  );
}

export default function NewsDetailPage() {
  const params = useParams();
  const router = useRouter();
  const newsId = Number(params.id);
  const invalidNewsId = Number.isNaN(newsId);

  const [article, setArticle] = useState<NewsArticle | null>(null);
  const [loading, setLoading] = useState(!invalidNewsId);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (invalidNewsId) {
      return;
    }

    fetchNewsDetail(newsId)
      .then((data) => {
        setArticle(data);
      })
      .catch(() => {
        setError("뉴스를 찾을 수 없습니다");
      })
      .finally(() => {
        setLoading(false);
      });
  }, [invalidNewsId, newsId]);

  if (invalidNewsId) {
    return (
      <div className="max-w-4xl mx-auto">
        <div className="rounded-lg border border-gray-800 bg-[#111111] p-8 text-center">
          <p className="text-sm text-gray-400">유효하지 않은 뉴스 ID</p>
          <button
            onClick={() => router.push("/news")}
            className="mt-4 rounded-lg bg-gray-800 px-4 py-2 text-sm text-white hover:bg-gray-700 transition-colors"
          >
            뉴스 목록으로 돌아가기
          </button>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="space-y-6 max-w-4xl mx-auto">
        <SkeletonBlock className="h-12" />
        <SkeletonBlock className="h-8" />
        <div className="grid grid-cols-2 gap-4">
          <SkeletonBlock className="h-32" />
          <SkeletonBlock className="h-32" />
        </div>
        <div className="grid grid-cols-3 gap-4">
          <SkeletonBlock className="h-36" />
          <SkeletonBlock className="h-36" />
          <SkeletonBlock className="h-36" />
        </div>
      </div>
    );
  }

  if (invalidNewsId || error || !article) {
    return (
      <div className="max-w-4xl mx-auto">
        <div className="rounded-lg border border-gray-800 bg-[#111111] p-8 text-center">
          <p className="text-sm text-gray-400">{invalidNewsId ? "유효하지 않은 뉴스 ID" : error ?? "뉴스를 찾을 수 없습니다"}</p>
          <button
            onClick={() => router.push("/news")}
            className="mt-4 rounded-lg bg-gray-800 px-4 py-2 text-sm text-white hover:bg-gray-700 transition-colors"
          >
            뉴스 목록으로 돌아가기
          </button>
        </div>
      </div>
    );
  }

  const sentimentScore = article.sentiment_score;
  const sentimentPct =
    sentimentScore != null ? Math.abs(sentimentScore) * 100 : 0;
  const sentimentText = sentimentLabelText(sentimentScore);
  const sentimentBarColor =
    sentimentScore != null && sentimentScore > 0
      ? "bg-green-500"
      : sentimentScore != null && sentimentScore < 0
        ? "bg-red-500"
        : "bg-gray-500";

  const category = article.news_category
    ? CATEGORY_LABELS[article.news_category]
    : null;

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* 헤더 */}
      <div>
        <div className="flex items-center gap-3 mb-4">
          <button
            onClick={() => router.push("/news")}
            className="text-sm text-gray-400 hover:text-white transition-colors"
          >
            &larr; 뉴스 목록
          </button>
          {category && (
            <span className={`rounded px-2 py-0.5 text-xs font-medium ${category.color}`}>
              {category.label}
            </span>
          )}
          {article.sector && (
            <span className="rounded bg-gray-700/50 px-2 py-0.5 text-xs text-gray-300">
              {article.sector}
            </span>
          )}
        </div>

        <h1 className="text-xl font-semibold text-white leading-relaxed">
          {article.title}
        </h1>

        <div className="mt-3 flex flex-wrap items-center gap-3 text-sm text-gray-400">
          <span className="font-medium text-gray-300">{article.source}</span>
          <span>|</span>
          <span>{formatDate(article.published_at)}</span>
          {article.url && (
            <>
              <span>|</span>
              <a
                href={article.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-400 hover:text-blue-300 transition-colors"
              >
                원문 보기 &rarr;
              </a>
            </>
          )}
        </div>
      </div>

      {/* 감성 분석 + 시장 영향 요약 */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {/* 감성 분석 */}
        <div className="rounded-lg border border-[#1f1f1f] bg-[#111111] p-5">
          <h3 className="text-sm font-medium text-gray-400 mb-4">감성 분석</h3>
          <div className="space-y-3">
            {/* 감성 바 */}
            <div className="relative h-3 rounded-full bg-gray-700 overflow-hidden">
              {sentimentScore != null && (
                <div
                  className={`absolute top-0 h-full rounded-full ${sentimentBarColor}`}
                  style={{
                    width: `${sentimentPct}%`,
                    left: sentimentScore >= 0 ? "50%" : `${50 - sentimentPct}%`,
                  }}
                />
              )}
              <div className="absolute top-0 left-1/2 h-full w-px bg-gray-500" />
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-400">
                {sentimentText} (확신도 {Math.round(sentimentPct)}%)
              </span>
              <span className={`text-lg font-bold tabular-nums ${
                sentimentScore != null && sentimentScore > 0
                  ? "text-green-400"
                  : sentimentScore != null && sentimentScore < 0
                    ? "text-red-400"
                    : "text-gray-400"
              }`}>
                {sentimentScore != null
                  ? `${sentimentScore >= 0 ? "+" : ""}${sentimentScore.toFixed(2)}`
                  : "-"}
              </span>
            </div>
          </div>
        </div>

        {/* 시장 영향 요약 */}
        {article.impact_summary && (
          <div className="rounded-lg border border-[#1f1f1f] bg-[#111111] p-5">
            <h3 className="text-sm font-medium text-gray-400 mb-4">시장 영향 요약</h3>
            <p className="text-sm text-gray-300 leading-relaxed">
              {article.impact_summary}
            </p>
            {article.impact_score != null && (
              <div className="mt-3 flex items-center gap-2">
                <span className="text-xs text-gray-500">영향 점수</span>
                <span className={`text-sm font-semibold tabular-nums ${
                  article.impact_score > 0 ? "text-green-400" :
                  article.impact_score < 0 ? "text-red-400" : "text-gray-400"
                }`}>
                  {article.impact_score >= 0 ? "+" : ""}{article.impact_score.toFixed(2)}
                </span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 영향 받는 종목 */}
      <div>
        <h2 className="text-lg font-semibold mb-4">영향 받는 종목</h2>
        {article.impacts && article.impacts.length > 0 ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {article.impacts.map((impact) => (
              <ImpactCard key={impact.stock_ticker} impact={impact} />
            ))}
          </div>
        ) : (
          <div className="rounded-lg border border-gray-800 bg-[#111111] p-6">
            <p className="text-sm text-gray-400">분석된 영향 종목이 없습니다.</p>
          </div>
        )}
      </div>

      <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-4 text-xs leading-relaxed text-amber-100">
        예상 영향은 뉴스 내용 기반 추정이고, 관측 반응은 일봉 기준 시장 대비 가격 움직임입니다.
        두 값은 인과관계나 투자 권유를 의미하지 않으며 데이터는 지연·정정될 수 있습니다.
      </div>
    </div>
  );
}
