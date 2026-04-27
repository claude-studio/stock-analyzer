"use client";

import { useEffect, useState } from "react";
import { APIError, fetchPersonalScreener } from "@/lib/api";
import type { ScreenerCandidate, ScreenerComponents, ScreenerResponse } from "@/lib/api";

function formatNumber(value: number | null | undefined, fractionDigits: number = 0): string {
  if (value == null) {
    return "-";
  }

  return value.toLocaleString("ko-KR", {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  });
}

function formatSignedNumber(
  value: number | null | undefined,
  suffix: string,
  fractionDigits: number = 1,
): string {
  if (value == null) {
    return "-";
  }

  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(fractionDigits)}${suffix}`;
}

function formatRecommendationLabel(recommendation: string | null | undefined): string {
  if (!recommendation) {
    return "일일 리포트 없음";
  }

  const normalized = recommendation.toLowerCase();
  if (normalized.includes("strong_buy")) return "강력 매수";
  if (normalized.includes("buy")) return "매수";
  if (normalized.includes("hold")) return "보유";
  if (normalized.includes("strong_sell")) return "강력 매도";
  if (normalized.includes("sell")) return "매도";
  return recommendation;
}

function recommendationTone(recommendation: string | null | undefined): string {
  if (!recommendation) {
    return "border-gray-700 bg-gray-800 text-gray-300";
  }

  const normalized = recommendation.toLowerCase();
  if (normalized.includes("strong_buy")) return "border-green-500/40 bg-green-500/15 text-green-300";
  if (normalized.includes("buy")) return "border-green-500/30 bg-green-500/10 text-green-300";
  if (normalized.includes("hold")) return "border-yellow-500/30 bg-yellow-500/10 text-yellow-300";
  if (normalized.includes("strong_sell")) return "border-red-500/40 bg-red-500/15 text-red-200";
  if (normalized.includes("sell")) return "border-red-500/30 bg-red-500/10 text-red-300";
  return "border-gray-700 bg-gray-800 text-gray-300";
}

function getErrorMessage(error: unknown): string {
  if (error instanceof APIError) {
    return error.detail ?? `스크리너 데이터를 불러오지 못했습니다. (${error.status})`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "스크리너 데이터를 불러오지 못했습니다.";
}

function MetricCard({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="rounded-lg border border-gray-800 bg-[#111111] p-5">
      <p className="text-xs font-medium uppercase tracking-[0.12em] text-gray-500">{label}</p>
      <p className="mt-3 text-2xl font-semibold tabular-nums text-white">{value}</p>
      {detail ? <p className="mt-2 text-xs leading-5 text-gray-500">{detail}</p> : null}
    </div>
  );
}

function ComponentCell({
  label,
  primary,
  secondary,
}: {
  label: string;
  primary: string;
  secondary: string;
}) {
  return (
    <div className="rounded-lg border border-gray-800 bg-[#0d0d0d] p-4">
      <p className="text-xs font-medium text-gray-500">{label}</p>
      <p className="mt-2 text-sm font-semibold tabular-nums text-white">{primary}</p>
      <p className="mt-1 text-xs text-gray-500">{secondary}</p>
    </div>
  );
}

function ScreenerSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="h-28 animate-pulse rounded-lg border border-gray-800 bg-gray-900" />
        ))}
      </div>
      {Array.from({ length: 2 }).map((_, index) => (
        <div key={index} className="h-80 animate-pulse rounded-lg border border-gray-800 bg-gray-900" />
      ))}
    </div>
  );
}

function CandidateCard({ candidate, rank }: { candidate: ScreenerCandidate; rank: number }) {
  const components: ScreenerComponents = candidate.components;

  return (
    <article className="rounded-lg border border-gray-800 bg-[#111111] p-5 sm:p-6">
      <div className="flex flex-col gap-4 border-b border-gray-800/80 pb-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <span className="inline-flex h-8 min-w-8 items-center justify-center rounded-full bg-sky-500/15 px-2 text-sm font-semibold text-sky-300">
              {rank}
            </span>
            <div>
              <h2 className="text-xl font-semibold tracking-tight text-white">{candidate.name}</h2>
              <p className="mt-1 text-sm text-gray-400">
                {candidate.ticker} · {candidate.market}
                {candidate.sector ? ` · ${candidate.sector}` : ""}
              </p>
            </div>
          </div>
          <p className="mt-3 text-sm leading-6 text-gray-300">
            저장된 데이터 범위 안에서 최근 가격·거래량·뉴스·최종 일일 리포트를 합쳐 본 후보입니다.
          </p>
        </div>

        <div className="flex flex-col items-start gap-3 lg:items-end">
          <div className="rounded-lg border border-gray-700 bg-[#0d0d0d] px-4 py-3 text-left lg:text-right">
            <p className="text-xs font-medium uppercase tracking-[0.12em] text-gray-500">종합 점수</p>
            <p className="mt-2 text-3xl font-semibold tabular-nums text-white">
              {candidate.score.toFixed(1)}
            </p>
          </div>
          <span className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium ${recommendationTone(candidate.latest_recommendation)}`}>
            {formatRecommendationLabel(candidate.latest_recommendation)}
          </span>
        </div>
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <ComponentCell
          label="가격 모멘텀"
          primary={formatSignedNumber(components.price_momentum_pct, "%")}
          secondary={`${formatSignedNumber(components.price_momentum_score, "점")} / ${candidate.latest_trade_date ?? "기준일 없음"}`}
        />
        <ComponentCell
          label="거래량 확산"
          primary={
            components.volume_spike_ratio == null
              ? "-"
              : `${components.volume_spike_ratio.toFixed(2)}배`
          }
          secondary={formatSignedNumber(components.volume_spike_score, "점")}
        />
        <ComponentCell
          label="최근 뉴스 밀도"
          primary={`${formatNumber(components.recent_news_count)}건`}
          secondary={`${formatSignedNumber(components.recent_news_score, "점")} / 최근 ${Math.max(candidate.reasons.filter((reason) => reason.includes("관련 뉴스")).length > 0 ? 7 : 0, 7)}일`}
        />
        <ComponentCell
          label="뉴스 영향 점수"
          primary={formatSignedNumber(components.avg_news_impact_score, "", 2)}
          secondary={formatSignedNumber(components.news_impact_score, "점")}
        />
        <ComponentCell
          label="최종 일일 리포트"
          primary={formatRecommendationLabel(components.latest_daily_recommendation)}
          secondary={`${formatSignedNumber(components.latest_daily_recommendation_score, "점")} / ${candidate.analysis_date ?? "리포트 없음"}`}
        />
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_260px]">
        <section className="rounded-lg border border-gray-800 bg-[#0d0d0d] p-4">
          <h3 className="text-sm font-semibold text-white">선정 이유</h3>
          <ul className="mt-3 space-y-2 text-sm leading-6 text-gray-300">
            {candidate.reasons.map((reason) => (
              <li key={reason} className="flex gap-2">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-sky-400" />
                <span>{reason}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="rounded-lg border border-gray-800 bg-[#0d0d0d] p-4">
          <h3 className="text-sm font-semibold text-white">기준 데이터</h3>
          <dl className="mt-3 space-y-3 text-sm text-gray-300">
            <div className="flex items-center justify-between gap-3">
              <dt className="text-gray-500">최신 종가</dt>
              <dd className="tabular-nums text-white">{formatNumber(candidate.latest_close)}</dd>
            </div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-gray-500">가격 기준일</dt>
              <dd className="tabular-nums text-white">{candidate.latest_trade_date ?? "-"}</dd>
            </div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-gray-500">일일 리포트 일자</dt>
              <dd className="tabular-nums text-white">{candidate.analysis_date ?? "-"}</dd>
            </div>
          </dl>
        </section>
      </div>
    </article>
  );
}

export default function ScreenerPage() {
  const [response, setResponse] = useState<ScreenerResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchPersonalScreener()
      .then((data) => {
        setResponse(data);
        setError(null);
      })
      .catch((nextError) => {
        setError(getErrorMessage(nextError));
        setResponse(null);
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  return (
    <div className="min-w-0 space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">개인 아이디어 스크리너</h1>
        <p className="mt-1 text-sm text-gray-400">
          현재 저장된 KRX 가격·뉴스·최종 일일 리포트를 바탕으로 탐색 후보를 정렬합니다.
        </p>
        <p className="mt-2 text-xs text-gray-500">
          전체 시장 랭킹이나 투자 자문이 아니라, 지금까지 수집된 데이터 범위 안에서 아이디어를 찾는 보조 도구입니다.
        </p>
      </div>

      <div className="rounded-lg border border-yellow-500/20 bg-yellow-500/5 px-4 py-3">
        <p className="text-sm text-yellow-300">
          KRX-first 개인용 스크리너입니다. 저장된 데이터 범위가 좁으면 후보가 비어 있을 수 있으며, 이는 기회가 없다는 뜻이 아닙니다.
        </p>
      </div>

      {loading ? (
        <ScreenerSkeleton />
      ) : error ? (
        <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-6">
          <p className="text-sm text-red-300">스크리너 데이터를 불러올 수 없습니다: {error}</p>
          <p className="mt-2 text-xs text-gray-500">API 서버가 실행 중인지, 그리고 `/api/v1/screener` 응답이 있는지 확인해 주세요.</p>
        </div>
      ) : response ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label="표시 후보"
              value={`${formatNumber(response.total_candidates)}개`}
              detail={`표시 제한 ${response.limit}개 / 아이디어 탐색용 정렬`}
            />
            <MetricCard
              label="랭킹 가능 종목"
              value={`${formatNumber(response.total_eligible)}개`}
              detail={`데이터 부족 ${formatNumber(response.total_insufficient)}개`}
            />
            <MetricCard
              label="최소 시세 포인트"
              value={`${formatNumber(response.minimum_price_points)}일`}
              detail={`최근 ${response.lookback_days}일 창에서 계산`}
            />
            <MetricCard
              label="기준 거래일"
              value={response.reference_trade_date ?? "-"}
              detail={`뉴스 관찰 창 ${response.news_window_days}일`}
            />
          </div>

          <section className="rounded-lg border border-gray-800 bg-[#111111] p-5 sm:p-6">
            <div className="flex flex-col gap-3 border-b border-gray-800/80 pb-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <h2 className="text-lg font-semibold tracking-tight text-white">커버리지와 제한 사항</h2>
                <p className="mt-1 text-sm text-gray-400">
                  저장된 종목 풀 안에서도 가격 포인트가 모자라면 랭킹에서 제외합니다.
                </p>
              </div>
              <div className="rounded-lg border border-gray-800 bg-[#0d0d0d] px-4 py-3 text-sm text-gray-300">
                <p>랭킹 시장: {response.coverage.ranked_markets.join(", ")}</p>
                <p className="mt-1 text-gray-500">제외 시장: {response.coverage.excluded_markets.join(", ")}</p>
              </div>
            </div>

            <ul className="mt-4 space-y-2 text-sm leading-6 text-gray-300">
              {response.limitations.map((limitation) => (
                <li key={limitation} className="flex gap-2">
                  <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-yellow-300" />
                  <span>{limitation}</span>
                </li>
              ))}
            </ul>
          </section>

          {response.candidates.length === 0 ? (
            <section className="rounded-lg border border-gray-800 bg-[#111111] p-6 text-center">
              <h2 className="text-lg font-semibold text-white">{response.empty_state.title}</h2>
              <p className="mx-auto mt-3 max-w-2xl text-sm leading-6 text-gray-400">
                {response.empty_state.description}
              </p>
              <div className="mt-4 inline-flex rounded-full border border-gray-700 bg-[#0d0d0d] px-4 py-2 text-xs text-gray-400">
                현재 저장 범위: 랭킹 가능 {response.total_eligible}개 / 데이터 부족 {response.total_insufficient}개
              </div>
            </section>
          ) : (
            <div className="space-y-4">
              {response.candidates.map((candidate, index) => (
                <CandidateCard key={candidate.ticker} candidate={candidate} rank={index + 1} />
              ))}
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
