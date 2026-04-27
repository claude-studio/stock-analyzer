"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  APIError,
  createPortfolioHolding,
  deletePortfolioHolding,
  fetchPortfolioSummary,
  updatePortfolioHolding,
} from "@/lib/api";
import type {
  PortfolioAllocationItem,
  PortfolioHolding,
  PortfolioSummary,
} from "@/lib/api";

interface HoldingFormState {
  ticker: string;
  quantity: string;
  averagePrice: string;
}

interface HoldingFormErrors {
  ticker?: string;
  quantity?: string;
  averagePrice?: string;
}

const INITIAL_FORM_STATE: HoldingFormState = {
  ticker: "",
  quantity: "",
  averagePrice: "",
};

function getCurrencyLocale(currency: string): string {
  if (currency === "USD") {
    return "en-US";
  }

  return "ko-KR";
}

function formatCurrency(value: number | null | undefined, currency: string): string {
  if (value == null) {
    return "-";
  }

  return new Intl.NumberFormat(getCurrencyLocale(currency), {
    style: "currency",
    currency,
    maximumFractionDigits: currency === "KRW" ? 0 : 2,
    minimumFractionDigits: currency === "KRW" ? 0 : 2,
  }).format(value);
}

function formatSignedCurrency(value: number | null | undefined, currency: string): string {
  if (value == null) {
    return "-";
  }

  return new Intl.NumberFormat(getCurrencyLocale(currency), {
    style: "currency",
    currency,
    signDisplay: "always",
    maximumFractionDigits: currency === "KRW" ? 0 : 2,
    minimumFractionDigits: currency === "KRW" ? 0 : 2,
  }).format(value);
}

function formatPercent(value: number | null | undefined): string {
  if (value == null) {
    return "-";
  }

  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

function formatQuantity(value: number | null | undefined): string {
  if (value == null) {
    return "-";
  }

  return value.toLocaleString("ko-KR", {
    maximumFractionDigits: 4,
  });
}

function normalizeDecimalInput(value: string): number {
  return Number(value.replaceAll(",", "").trim());
}

function validateHoldingForm(form: HoldingFormState): HoldingFormErrors {
  const errors: HoldingFormErrors = {};
  const ticker = form.ticker.trim().toUpperCase();

  if (!ticker) {
    errors.ticker = "티커를 입력해 주세요.";
  } else if (!/^[A-Z0-9.-]+$/.test(ticker)) {
    errors.ticker = "티커는 영문 대문자, 숫자, 점(.), 하이픈(-)만 사용할 수 있습니다.";
  }

  const quantity = normalizeDecimalInput(form.quantity);
  if (!Number.isFinite(quantity)) {
    errors.quantity = "수량은 숫자로 입력해 주세요.";
  } else if (quantity <= 0) {
    errors.quantity = "수량은 0보다 커야 합니다.";
  }

  const averagePrice = normalizeDecimalInput(form.averagePrice);
  if (!Number.isFinite(averagePrice)) {
    errors.averagePrice = "평균 단가는 숫자로 입력해 주세요.";
  } else if (averagePrice <= 0) {
    errors.averagePrice = "평균 단가는 0보다 커야 합니다.";
  }

  return errors;
}

function getMarketLabel(market: string): { label: string; className: string } {
  const normalized = market.toUpperCase();
  if (["KRX", "KOSPI", "KOSDAQ"].includes(normalized)) {
    return {
      label: "KRX",
      className: "border border-emerald-500/20 bg-emerald-500/10 text-emerald-300",
    };
  }

  return {
    label: "US",
    className: "border border-sky-500/20 bg-sky-500/10 text-sky-300",
  };
}

function getPnlColor(value: number | null | undefined): string {
  if (value == null) {
    return "text-gray-500";
  }
  if (value > 0) {
    return "text-green-400";
  }
  if (value < 0) {
    return "text-red-400";
  }
  return "text-gray-300";
}

function getPortfolioErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof APIError) {
    if (error.detail) {
      return error.detail;
    }

    if (error.status === 404) {
      return "등록 가능한 종목을 찾지 못했습니다. 티커를 다시 확인해 주세요.";
    }

    if (error.status === 409) {
      return "이미 등록된 보유 종목입니다.";
    }

    return `요청을 처리하지 못했습니다. (${error.status})`;
  }

  if (error instanceof Error && error.message) {
    return error.message;
  }

  return fallback;
}

function SectionCard({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-gray-800 bg-[#111111] p-5 sm:p-6">
      <div className="flex flex-col gap-3 border-b border-gray-800/80 pb-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-white">{title}</h2>
          {description ? (
            <p className="mt-1 text-sm leading-6 text-gray-400">{description}</p>
          ) : null}
        </div>
        {actions ? <div className="shrink-0">{actions}</div> : null}
      </div>
      <div className="mt-5">{children}</div>
    </section>
  );
}

function MetricCard({
  label,
  value,
  tone = "default",
  detail,
}: {
  label: string;
  value: string;
  tone?: "default" | "positive" | "negative" | "muted";
  detail?: string;
}) {
  const toneClass =
    tone === "positive"
      ? "text-green-400"
      : tone === "negative"
        ? "text-red-400"
        : tone === "muted"
          ? "text-gray-500"
          : "text-white";

  return (
    <div className="rounded-lg border border-gray-800 bg-[#0d0d0d] p-4">
      <p className="text-xs font-medium uppercase tracking-[0.12em] text-gray-500">{label}</p>
      <p className={`mt-3 text-2xl font-semibold tabular-nums ${toneClass}`}>{value}</p>
      {detail ? <p className="mt-2 text-xs leading-5 text-gray-500">{detail}</p> : null}
    </div>
  );
}

function SummarySkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <div
            key={index}
            className="h-28 animate-pulse rounded-lg border border-gray-800 bg-gray-900"
          />
        ))}
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        {Array.from({ length: 2 }).map((_, index) => (
          <div
            key={index}
            className="h-40 animate-pulse rounded-lg border border-gray-800 bg-gray-900"
          />
        ))}
      </div>
    </div>
  );
}

export default function PortfolioDashboard() {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [formState, setFormState] = useState<HoldingFormState>(INITIAL_FORM_STATE);
  const [formErrors, setFormErrors] = useState<HoldingFormErrors>({});
  const [formMessage, setFormMessage] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [editingHoldingId, setEditingHoldingId] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [deletingHoldingId, setDeletingHoldingId] = useState<number | null>(null);

  const refreshPortfolio = useCallback(async () => {
    try {
      const nextSummary = await fetchPortfolioSummary();
      setSummary(nextSummary);
      setError(null);
    } catch (refreshError) {
      const message = getPortfolioErrorMessage(
        refreshError,
        "포트폴리오 데이터를 불러오지 못했습니다. API 서버 상태를 확인해 주세요.",
      );
      setError(message);
      throw new Error(message, { cause: refreshError });
    }
  }, []);

  useEffect(() => {
    let active = true;

    async function initializePortfolio() {
      try {
        const nextSummary = await fetchPortfolioSummary();
        if (!active) {
          return;
        }

        setSummary(nextSummary);
        setError(null);
      } catch (loadError) {
        if (!active) {
          return;
        }

        setError(
          getPortfolioErrorMessage(
            loadError,
            "포트폴리오 데이터를 불러오지 못했습니다. API 서버 상태를 확인해 주세요.",
          ),
        );
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    void initializePortfolio();

    return () => {
      active = false;
    };
  }, []);

  const holdings = summary?.holdings ?? [];
  const allocation = summary?.allocation ?? [];
  const primaryCurrency = holdings[0]?.currency ?? "KRW";

  const statusMessages = useMemo(() => {
    if (!summary) {
      return [] as string[];
    }

    const nextMessages: string[] = [];

    if (summary.has_mixed_currencies) {
      nextMessages.push(
        "KRW와 USD를 합산하지 않고 통화별로 분리해 보여줍니다. 원화 환산이나 통합 수익률은 제공하지 않습니다.",
      );
    }

    if (summary.has_missing_prices) {
      nextMessages.push(
        "일부 종목의 최신 종가를 찾지 못해 평가액, 손익, 비중이 비어 있는 항목이 있습니다.",
      );
    }

    if (holdings.length === 0) {
      nextMessages.push("수동 입력 기준 포트폴리오입니다. 브로커 연동, 세금 lot, 자동 리밸런싱은 아직 지원하지 않습니다.");
    }

    return nextMessages;
  }, [holdings.length, summary]);

  function resetForm() {
    setFormState(INITIAL_FORM_STATE);
    setFormErrors({});
    setFormError(null);
    setFormMessage(null);
    setEditingHoldingId(null);
  }

  function startEdit(holding: PortfolioHolding) {
    setEditingHoldingId(holding.id);
    setFormState({
      ticker: holding.ticker,
      quantity: String(holding.quantity),
      averagePrice: String(holding.average_price),
    });
    setFormErrors({});
    setFormError(null);
    setFormMessage(null);
  }

  async function handleSubmit(event: { preventDefault(): void }) {
    event.preventDefault();
    const nextErrors = validateHoldingForm(formState);
    setFormErrors(nextErrors);
    setFormError(null);
    setFormMessage(null);

    if (Object.keys(nextErrors).length > 0) {
      return;
    }

    const payload = {
      ticker: formState.ticker.trim().toUpperCase(),
      quantity: normalizeDecimalInput(formState.quantity),
      average_price: normalizeDecimalInput(formState.averagePrice),
    };

    setSubmitting(true);

    try {
      if (editingHoldingId == null) {
        await createPortfolioHolding(payload);
      } else {
        await updatePortfolioHolding(editingHoldingId, payload);
      }

      await refreshPortfolio();
      setFormState(INITIAL_FORM_STATE);
      setFormErrors({});
      setEditingHoldingId(null);
      setFormMessage(
        editingHoldingId == null
          ? "보유 종목을 추가했습니다."
          : "보유 종목을 수정했습니다.",
      );
    } catch (submitError) {
      setFormError(
        getPortfolioErrorMessage(
          submitError,
          editingHoldingId == null
            ? "보유 종목을 추가하지 못했습니다."
            : "보유 종목을 수정하지 못했습니다.",
        ),
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(holding: PortfolioHolding) {
    const confirmed = window.confirm(`${holding.name}(${holding.ticker}) 보유 종목을 삭제할까요?`);
    if (!confirmed) {
      return;
    }

    setDeletingHoldingId(holding.id);
    setFormError(null);
    setFormMessage(null);

    try {
      await deletePortfolioHolding(holding.id);
      await refreshPortfolio();
      if (editingHoldingId === holding.id) {
        resetForm();
      }
      setFormMessage("보유 종목을 삭제했습니다.");
    } catch (deleteError) {
      setFormError(
        getPortfolioErrorMessage(deleteError, "보유 종목을 삭제하지 못했습니다."),
      );
    } finally {
      setDeletingHoldingId(null);
    }
  }

  function renderSummaryValue(value: number | null, emptyFallback: string): string {
    if (holdings.length === 0) {
      return emptyFallback;
    }

    if (value == null) {
      return "계산 불가";
    }

    return formatCurrency(value, primaryCurrency);
  }

  function getAllocationHint(item: PortfolioAllocationItem): string {
    if (item.is_price_missing) {
      return "최신가 없음";
    }

    if (summary?.has_mixed_currencies) {
      return "통화 분리";
    }

    return "계산 불가";
  }

  return (
    <div className="min-w-0 space-y-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-white">포트폴리오</h1>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-gray-400">
            수동 입력 기준으로 보유 종목의 매수 원가, 최신 평가액, 미실현 손익을 추적합니다.
            종가가 비어 있거나 KRW/USD가 섞여 있으면 그 한계를 그대로 보여줍니다.
          </p>
        </div>

        <div className="flex flex-wrap gap-2 text-xs font-medium text-gray-300">
          <span className="rounded-full border border-gray-700 bg-[#0d0d0d] px-3 py-1.5">
            수동 관리
          </span>
          {summary?.has_mixed_currencies ? (
            <span className="rounded-full border border-sky-500/20 bg-sky-500/10 px-3 py-1.5 text-sky-300">
              혼합 통화 분리 표시
            </span>
          ) : null}
          {summary?.has_missing_prices ? (
            <span className="rounded-full border border-amber-500/20 bg-amber-500/10 px-3 py-1.5 text-amber-300">
              최신가 누락 있음
            </span>
          ) : null}
        </div>
      </div>

      {error ? (
        <div className="rounded-lg border border-red-500/20 bg-red-500/5 px-4 py-3">
          <p className="text-sm text-red-300">{error}</p>
          <p className="mt-1 text-xs text-gray-500">
            로컬 백엔드나 브라우저 fetch mock이 준비되어 있는지 확인해 주세요.
          </p>
        </div>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.7fr)_minmax(320px,0.9fr)]">
        <div className="space-y-6">
          <SectionCard
            title="포트폴리오 개요"
            description="합산 가능한 경우에는 총액을, 그렇지 않은 경우에는 왜 비워 두는지 함께 표시합니다."
          >
            {loading ? (
              <SummarySkeleton />
            ) : (
              <div className="space-y-5">
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  <MetricCard
                    label="보유 종목"
                    value={`${holdings.length.toLocaleString("ko-KR")}개`}
                    detail="중복 티커 없이 종목별 1건만 보유합니다."
                  />
                  <MetricCard
                    label="총 매수 원가"
                    value={renderSummaryValue(summary?.invested_amount ?? null, "0")}
                    tone={summary?.invested_amount == null && holdings.length > 0 ? "muted" : "default"}
                    detail={summary?.has_mixed_currencies ? "혼합 통화에서는 통합 합계를 만들지 않습니다." : undefined}
                  />
                  <MetricCard
                    label="현재 평가액"
                    value={renderSummaryValue(summary?.latest_valuation ?? null, "0")}
                    tone={summary?.latest_valuation == null && holdings.length > 0 ? "muted" : "default"}
                    detail={summary?.has_missing_prices ? "최신 종가가 없는 종목은 평가액에서 제외하지 않고 전체를 비워 둡니다." : undefined}
                  />
                  <MetricCard
                    label="미실현 손익"
                    value={
                      summary?.unrealized_pnl == null && holdings.length > 0
                        ? "계산 불가"
                        : holdings.length === 0
                          ? "0"
                          : formatSignedCurrency(summary?.unrealized_pnl, primaryCurrency)
                    }
                    tone={
                      summary?.unrealized_pnl == null
                        ? holdings.length > 0
                          ? "muted"
                          : "default"
                        : summary.unrealized_pnl > 0
                          ? "positive"
                          : summary.unrealized_pnl < 0
                            ? "negative"
                            : "default"
                    }
                    detail={
                      summary?.unrealized_pnl_percent == null
                        ? holdings.length > 0
                          ? "손익률도 함께 비워 둡니다."
                          : undefined
                        : formatPercent(summary.unrealized_pnl_percent)
                    }
                  />
                </div>

                {statusMessages.length > 0 ? (
                  <div className="rounded-lg border border-gray-800 bg-[#0d0d0d] px-4 py-3">
                    <ul className="space-y-1.5 text-sm leading-6 text-gray-400">
                      {statusMessages.map((message) => (
                        <li key={message} className="flex gap-2">
                          <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-gray-600" />
                          <span>{message}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                <div className="grid gap-3 lg:grid-cols-2">
                  {(summary?.currency_breakdown ?? []).map((bucket) => (
                    <div
                      key={bucket.currency}
                      className="rounded-lg border border-gray-800 bg-[#0d0d0d] p-4"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="text-xs font-medium uppercase tracking-[0.12em] text-gray-500">
                            {bucket.currency} 버킷
                          </p>
                          <p className="mt-2 text-xl font-semibold text-white">
                            {formatCurrency(bucket.invested_amount, bucket.currency)}
                          </p>
                        </div>
                        <span className="rounded-full border border-gray-700 px-2.5 py-1 text-xs font-medium text-gray-300">
                          {bucket.currency}
                        </span>
                      </div>

                      <dl className="mt-4 space-y-2 text-sm">
                        <div className="flex items-center justify-between gap-4">
                          <dt className="text-gray-500">현재 평가액</dt>
                          <dd className="tabular-nums text-right text-white">
                            {bucket.has_missing_prices
                              ? "최신 종가 없음"
                              : formatCurrency(bucket.latest_valuation, bucket.currency)}
                          </dd>
                        </div>
                        <div className="flex items-center justify-between gap-4">
                          <dt className="text-gray-500">미실현 손익</dt>
                          <dd className={`tabular-nums text-right ${getPnlColor(bucket.unrealized_pnl)}`}>
                            {bucket.has_missing_prices
                              ? "계산 불가"
                              : formatSignedCurrency(bucket.unrealized_pnl, bucket.currency)}
                          </dd>
                        </div>
                        <div className="flex items-center justify-between gap-4">
                          <dt className="text-gray-500">손익률</dt>
                          <dd className={`tabular-nums text-right ${getPnlColor(bucket.unrealized_pnl_percent)}`}>
                            {bucket.has_missing_prices ? "계산 불가" : formatPercent(bucket.unrealized_pnl_percent)}
                          </dd>
                        </div>
                      </dl>
                    </div>
                  ))}

                  {!summary?.currency_breakdown.length ? (
                    <div className="rounded-lg border border-dashed border-gray-800 bg-[#0d0d0d] px-4 py-6 text-sm text-gray-500 lg:col-span-2">
                      아직 집계할 보유 종목이 없습니다.
                    </div>
                  ) : null}
                </div>
              </div>
            )}
          </SectionCard>

          <SectionCard
            title="보유 종목"
            description="종목 단위 원가와 최신 종가를 함께 보며, 수정/삭제 후 전체 요약을 다시 계산합니다."
            actions={
              <p className="text-xs text-gray-500 tabular-nums">
                총 {holdings.length.toLocaleString("ko-KR")}개
              </p>
            }
          >
            {loading ? (
              <div className="space-y-3">
                {Array.from({ length: 4 }).map((_, index) => (
                  <div
                    key={index}
                    className="h-16 animate-pulse rounded-lg border border-gray-800 bg-gray-900"
                  />
                ))}
              </div>
            ) : holdings.length === 0 ? (
              <div className="rounded-lg border border-dashed border-gray-800 bg-[#0d0d0d] px-4 py-8 text-center">
                <p className="text-sm text-gray-300">등록된 보유 종목이 없습니다.</p>
                <p className="mt-1 text-xs leading-5 text-gray-500">
                  오른쪽 입력 폼에서 KRX 또는 미국 주식 티커를 직접 추가해 주세요.
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-gray-800">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-800 bg-[#0d0d0d]">
                      <th className="px-4 py-3 text-left font-medium text-gray-400">종목</th>
                      <th className="px-4 py-3 text-left font-medium text-gray-400">구분</th>
                      <th className="px-4 py-3 text-right font-medium text-gray-400">수량</th>
                      <th className="px-4 py-3 text-right font-medium text-gray-400">평균 단가</th>
                      <th className="px-4 py-3 text-right font-medium text-gray-400">매수 원가</th>
                      <th className="px-4 py-3 text-right font-medium text-gray-400">최신 종가</th>
                      <th className="px-4 py-3 text-right font-medium text-gray-400">현재 평가액</th>
                      <th className="px-4 py-3 text-right font-medium text-gray-400">미실현 손익</th>
                      <th className="px-4 py-3 text-right font-medium text-gray-400">비중</th>
                      <th className="px-4 py-3 text-right font-medium text-gray-400">관리</th>
                    </tr>
                  </thead>
                  <tbody>
                    {holdings.map((holding) => {
                      const marketLabel = getMarketLabel(holding.market);

                      return (
                        <tr
                          key={holding.id}
                          className="border-b border-gray-800/60 align-top transition-colors hover:bg-gray-800/20"
                        >
                          <td className="px-4 py-3">
                            <div className="min-w-[180px]">
                              <Link
                                href={`/stocks/${holding.ticker}`}
                                className="font-medium text-white transition-colors hover:text-green-400"
                              >
                                {holding.name}
                              </Link>
                              <div className="mt-1 flex items-center gap-2 text-xs text-gray-500">
                                <span className="font-mono text-green-500">{holding.ticker}</span>
                                <span>·</span>
                                <span>{holding.market}</span>
                              </div>
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex min-w-[118px] flex-wrap gap-2">
                              <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${marketLabel.className}`}>
                                {marketLabel.label}
                              </span>
                              <span className="rounded-full border border-gray-700 px-2.5 py-1 text-xs font-medium text-gray-300">
                                {holding.currency}
                              </span>
                            </div>
                          </td>
                          <td className="px-4 py-3 text-right tabular-nums text-white">
                            {formatQuantity(holding.quantity)}
                          </td>
                          <td className="px-4 py-3 text-right tabular-nums text-white">
                            {formatCurrency(holding.average_price, holding.currency)}
                          </td>
                          <td className="px-4 py-3 text-right tabular-nums text-gray-300">
                            {formatCurrency(holding.invested_amount, holding.currency)}
                          </td>
                          <td className="px-4 py-3 text-right">
                            {holding.is_price_missing ? (
                              <div className="min-w-[120px] text-xs leading-5 text-amber-300">
                                <p>최신 종가 없음</p>
                                <p className="text-gray-500">수동 확인 필요</p>
                              </div>
                            ) : (
                              <div className="min-w-[120px]">
                                <p className="tabular-nums text-white">
                                  {formatCurrency(holding.latest_price, holding.currency)}
                                </p>
                                <p className="mt-1 text-xs text-gray-500">
                                  {holding.latest_trade_date ?? "날짜 미확인"}
                                </p>
                              </div>
                            )}
                          </td>
                          <td className="px-4 py-3 text-right tabular-nums text-white">
                            {holding.is_price_missing
                              ? "계산 불가"
                              : formatCurrency(holding.latest_valuation, holding.currency)}
                          </td>
                          <td className="px-4 py-3 text-right">
                            {holding.is_price_missing ? (
                              <div className="text-xs leading-5 text-gray-500">
                                <p>최신가 누락</p>
                                <p>손익 미표시</p>
                              </div>
                            ) : (
                              <div className={`tabular-nums ${getPnlColor(holding.unrealized_pnl)}`}>
                                <p>{formatSignedCurrency(holding.unrealized_pnl, holding.currency)}</p>
                                <p className="mt-1 text-xs">{formatPercent(holding.unrealized_pnl_percent)}</p>
                              </div>
                            )}
                          </td>
                          <td className="px-4 py-3 text-right">
                            {holding.allocation_percent == null ? (
                              <div className="text-xs leading-5 text-gray-500">
                                <p>{holding.is_price_missing ? "최신가 없음" : "통화 분리"}</p>
                                <p>비중 미계산</p>
                              </div>
                            ) : (
                              <span className="tabular-nums text-gray-200">
                                {formatPercent(holding.allocation_percent)}
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex min-w-[132px] justify-end gap-2">
                              <button
                                type="button"
                                onClick={() => startEdit(holding)}
                                className="rounded-lg border border-gray-700 px-3 py-2 text-xs font-medium text-gray-200 transition-colors hover:border-gray-500 hover:text-white"
                              >
                                수정
                              </button>
                              <button
                                type="button"
                                onClick={() => void handleDelete(holding)}
                                disabled={deletingHoldingId === holding.id}
                                className="rounded-lg border border-red-500/20 px-3 py-2 text-xs font-medium text-red-300 transition-colors hover:border-red-400/40 hover:text-red-200 disabled:cursor-not-allowed disabled:opacity-60"
                              >
                                {deletingHoldingId === holding.id ? "삭제 중..." : "삭제"}
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </SectionCard>

          <SectionCard
            title="비중 보기"
            description="비중이 계산 가능한 경우에만 막대를 보여 주고, 그렇지 않으면 이유를 그대로 남깁니다."
          >
            {loading ? (
              <div className="space-y-3">
                {Array.from({ length: 4 }).map((_, index) => (
                  <div
                    key={index}
                    className="h-14 animate-pulse rounded-lg border border-gray-800 bg-gray-900"
                  />
                ))}
              </div>
            ) : allocation.length === 0 ? (
              <div className="rounded-lg border border-dashed border-gray-800 bg-[#0d0d0d] px-4 py-6 text-sm text-gray-500">
                아직 비중을 계산할 보유 종목이 없습니다.
              </div>
            ) : (
              <div className="space-y-3">
                {allocation.map((item) => (
                  <div key={item.holding_id} className="rounded-lg border border-gray-800 bg-[#0d0d0d] p-4">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div>
                        <div className="flex items-center gap-2">
                          <Link
                            href={`/stocks/${item.ticker}`}
                            className="font-medium text-white transition-colors hover:text-green-400"
                          >
                            {item.name}
                          </Link>
                          <span className="font-mono text-xs text-green-500">{item.ticker}</span>
                        </div>
                        <p className="mt-1 text-xs text-gray-500">
                          {getMarketLabel(item.market).label} · {item.currency}
                        </p>
                      </div>

                      <div className="text-left sm:text-right">
                        <p className="tabular-nums text-sm text-white">
                          {item.latest_valuation == null
                            ? "평가액 없음"
                            : formatCurrency(item.latest_valuation, item.currency)}
                        </p>
                        <p className="mt-1 text-xs text-gray-500">
                          {item.allocation_percent == null
                            ? getAllocationHint(item)
                            : `${item.allocation_percent.toFixed(2)}%`}
                        </p>
                      </div>
                    </div>

                    <div className="mt-4">
                      {item.allocation_percent == null ? (
                        <div className="rounded-full border border-dashed border-gray-700 px-3 py-2 text-xs text-gray-500">
                          {getAllocationHint(item)} 때문에 전체 비중 막대를 만들지 않았습니다.
                        </div>
                      ) : (
                        <>
                          <div className="h-2 overflow-hidden rounded-full bg-gray-800">
                            <div
                              className="h-full rounded-full bg-green-500"
                              style={{ width: `${Math.min(item.allocation_percent, 100)}%` }}
                            />
                          </div>
                          <div className="mt-2 flex items-center justify-between text-xs text-gray-500">
                            <span>포트폴리오 비중</span>
                            <span className="tabular-nums text-gray-300">
                              {item.allocation_percent.toFixed(2)}%
                            </span>
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </SectionCard>
        </div>

        <aside className="space-y-6">
          <SectionCard
            title={editingHoldingId == null ? "보유 종목 추가" : "보유 종목 수정"}
            description={
              editingHoldingId == null
                ? "티커, 수량, 평균 단가를 입력하면 즉시 요약과 비중을 다시 계산합니다."
                : "현재 보유 값으로 폼을 채웠습니다. 저장하면 요약과 비중을 다시 불러옵니다."
            }
          >
            <form className="space-y-4" onSubmit={(event) => void handleSubmit(event)}>
              <div className="space-y-2">
                <label htmlFor="portfolio-ticker" className="text-sm font-medium text-gray-200">
                  티커
                </label>
                <input
                  id="portfolio-ticker"
                  type="text"
                  value={formState.ticker}
                  onChange={(event) => {
                    setFormState((current) => ({
                      ...current,
                      ticker: event.target.value.toUpperCase(),
                    }));
                  }}
                  placeholder="예: 005930 / AAPL"
                  className="w-full rounded-lg border border-gray-800 bg-[#0d0d0d] px-4 py-2.5 text-sm text-white outline-none transition-colors placeholder:text-gray-500 focus:border-gray-600"
                  aria-invalid={Boolean(formErrors.ticker)}
                  aria-describedby={formErrors.ticker ? "portfolio-ticker-error" : undefined}
                />
                {formErrors.ticker ? (
                  <p id="portfolio-ticker-error" className="text-xs text-red-300">
                    {formErrors.ticker}
                  </p>
                ) : (
                  <p className="text-xs text-gray-500">등록된 종목 티커만 입력할 수 있습니다.</p>
                )}
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <label htmlFor="portfolio-quantity" className="text-sm font-medium text-gray-200">
                    수량
                  </label>
                  <input
                    id="portfolio-quantity"
                    type="text"
                    inputMode="decimal"
                    value={formState.quantity}
                    onChange={(event) => {
                      setFormState((current) => ({
                        ...current,
                        quantity: event.target.value,
                      }));
                    }}
                    placeholder="10"
                    className="w-full rounded-lg border border-gray-800 bg-[#0d0d0d] px-4 py-2.5 text-sm text-white outline-none transition-colors placeholder:text-gray-500 focus:border-gray-600"
                    aria-invalid={Boolean(formErrors.quantity)}
                    aria-describedby={formErrors.quantity ? "portfolio-quantity-error" : undefined}
                  />
                  {formErrors.quantity ? (
                    <p id="portfolio-quantity-error" className="text-xs text-red-300">
                      {formErrors.quantity}
                    </p>
                  ) : null}
                </div>

                <div className="space-y-2">
                  <label htmlFor="portfolio-average-price" className="text-sm font-medium text-gray-200">
                    평균 단가
                  </label>
                  <input
                    id="portfolio-average-price"
                    type="text"
                    inputMode="decimal"
                    value={formState.averagePrice}
                    onChange={(event) => {
                      setFormState((current) => ({
                        ...current,
                        averagePrice: event.target.value,
                      }));
                    }}
                    placeholder="70000 또는 150.25"
                    className="w-full rounded-lg border border-gray-800 bg-[#0d0d0d] px-4 py-2.5 text-sm text-white outline-none transition-colors placeholder:text-gray-500 focus:border-gray-600"
                    aria-invalid={Boolean(formErrors.averagePrice)}
                    aria-describedby={formErrors.averagePrice ? "portfolio-average-price-error" : undefined}
                  />
                  {formErrors.averagePrice ? (
                    <p id="portfolio-average-price-error" className="text-xs text-red-300">
                      {formErrors.averagePrice}
                    </p>
                  ) : null}
                </div>
              </div>

              {formMessage ? (
                <div className="rounded-lg border border-green-500/20 bg-green-500/5 px-4 py-3 text-sm text-green-300">
                  {formMessage}
                </div>
              ) : null}

              {formError ? (
                <div className="rounded-lg border border-red-500/20 bg-red-500/5 px-4 py-3 text-sm text-red-300">
                  {formError}
                </div>
              ) : null}

              <div className="flex flex-col gap-2 sm:flex-row">
                <button
                  type="submit"
                  disabled={submitting}
                  className="inline-flex min-h-11 items-center justify-center rounded-lg bg-green-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-green-500 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {submitting
                    ? editingHoldingId == null
                      ? "추가 중..."
                      : "저장 중..."
                    : editingHoldingId == null
                      ? "보유 종목 추가"
                      : "수정 내용 저장"}
                </button>
                {editingHoldingId != null ? (
                  <button
                    type="button"
                    onClick={resetForm}
                    className="inline-flex min-h-11 items-center justify-center rounded-lg border border-gray-700 px-4 py-2.5 text-sm font-medium text-gray-200 transition-colors hover:border-gray-500 hover:text-white"
                  >
                    수정 취소
                  </button>
                ) : null}
              </div>
            </form>
          </SectionCard>

          <SectionCard
            title="표시 기준"
            description="숫자를 예쁘게 꾸미기보다, 현재 추적 가능한 범위를 정확히 보여 주는 데 집중합니다."
          >
            <ul className="space-y-3 text-sm leading-6 text-gray-400">
              <li className="flex gap-2">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-gray-600" />
                <span>최신 일봉 종가가 없는 종목은 평가액과 손익을 비워 두고, 테이블과 비중 영역에서 이유를 직접 표시합니다.</span>
              </li>
              <li className="flex gap-2">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-gray-600" />
                <span>KRW와 USD 보유가 섞이면 통화별 버킷만 보여 주고, 원화 환산이나 통합 손익률은 제공하지 않습니다.</span>
              </li>
              <li className="flex gap-2">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-gray-600" />
                <span>현재 버전은 수동 입력 전용입니다. 브로커 동기화, 자동 리밸런싱, tax lot 관리는 범위에 포함하지 않습니다.</span>
              </li>
            </ul>
          </SectionCard>
        </aside>
      </div>
    </div>
  );
}
