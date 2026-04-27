"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  APIError,
  createAlertRule,
  deleteAlertRule,
  evaluateAlertRules,
  fetchAlertEvents,
  fetchAlertRules,
  runBacktest,
  updateAlertRule,
} from "@/lib/api";
import type {
  AlertEvaluationResponse,
  AlertEvent,
  AlertRule,
  BacktestRunResponse,
} from "@/lib/api";

interface BacktestFormState {
  ticker: string;
  startDate: string;
  endDate: string;
  initialCapital: string;
}

interface AlertFormState {
  ticker: string;
  name: string;
  ruleType: "target_price" | "rsi_threshold" | "sentiment_change" | "recommendation_change";
  direction: string;
  thresholdValue: string;
  targetRecommendation: string;
  lookbackDays: string;
}

interface FormErrors {
  ticker?: string;
  name?: string;
  thresholdValue?: string;
  initialCapital?: string;
}

function formatLocalDateForInput(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function getTodayDateString(): string {
  return formatLocalDateForInput(new Date());
}

function getDefaultStartDateString(): string {
  const target = new Date();
  target.setDate(target.getDate() - 30);
  return formatLocalDateForInput(target);
}

const INITIAL_BACKTEST_FORM: BacktestFormState = {
  ticker: "005930",
  startDate: getDefaultStartDateString(),
  endDate: getTodayDateString(),
  initialCapital: "100000",
};

const INITIAL_ALERT_FORM: AlertFormState = {
  ticker: "005930",
  name: "",
  ruleType: "target_price",
  direction: "above",
  thresholdValue: "",
  targetRecommendation: "buy",
  lookbackDays: "2",
};

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof APIError) {
    return error.detail ?? `${fallback} (${error.status})`;
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

function formatNumber(value: number | null | undefined, fractionDigits: number = 0): string {
  if (value == null) {
    return "-";
  }

  return value.toLocaleString("ko-KR", {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  });
}

function formatPercent(value: number | null | undefined): string {
  if (value == null) {
    return "-";
  }

  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

function formatRecommendationLabel(recommendation: string | null | undefined): string {
  if (!recommendation) {
    return "-";
  }

  const normalized = recommendation.toLowerCase();
  if (normalized.includes("strong_buy")) return "강력 매수";
  if (normalized.includes("buy")) return "매수";
  if (normalized.includes("hold")) return "보유";
  if (normalized.includes("strong_sell")) return "강력 매도";
  if (normalized.includes("sell")) return "매도";
  return recommendation;
}

function formatRuleType(ruleType: string): string {
  if (ruleType === "target_price") return "목표가";
  if (ruleType === "rsi_threshold") return "RSI";
  if (ruleType === "sentiment_change") return "감성 변화";
  if (ruleType === "recommendation_change") return "추천 변화";
  return ruleType;
}

function formatDirection(direction: string | null | undefined): string {
  if (direction === "above") return "이상";
  if (direction === "below") return "이하";
  if (direction === "up") return "상승";
  if (direction === "down") return "하락";
  return "-";
}

function getBacktestTone(value: number): string {
  if (value > 0) return "text-green-400";
  if (value < 0) return "text-red-400";
  return "text-gray-300";
}

function validateBacktestForm(form: BacktestFormState): FormErrors {
  const errors: FormErrors = {};
  if (!form.ticker.trim()) {
    errors.ticker = "티커를 입력해 주세요.";
  }

  const capital = Number(form.initialCapital.replaceAll(",", "").trim());
  if (!Number.isFinite(capital) || capital <= 0) {
    errors.initialCapital = "초기 자본은 0보다 큰 숫자여야 합니다.";
  }

  return errors;
}

function validateAlertForm(form: AlertFormState): FormErrors {
  const errors: FormErrors = {};
  if (!form.ticker.trim()) {
    errors.ticker = "티커를 입력해 주세요.";
  }
  if (!form.name.trim()) {
    errors.name = "규칙 이름을 입력해 주세요.";
  }
  if (form.ruleType !== "recommendation_change") {
    const threshold = Number(form.thresholdValue.trim());
    if (!Number.isFinite(threshold) || threshold <= 0) {
      errors.thresholdValue = "임계값은 0보다 큰 숫자여야 합니다.";
    }
  }
  return errors;
}

function SectionCard({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-gray-800 bg-[#111111] p-5 sm:p-6">
      <div className="flex flex-col gap-3 border-b border-gray-800/80 pb-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-white">{title}</h2>
          <p className="mt-1 text-sm leading-6 text-gray-400">{description}</p>
        </div>
        {actions ? <div className="shrink-0">{actions}</div> : null}
      </div>
      <div className="mt-5">{children}</div>
    </section>
  );
}

function MetricCard({ label, value, detail, toneClass = "text-white" }: { label: string; value: string; detail?: string; toneClass?: string }) {
  return (
    <div className="rounded-lg border border-gray-800 bg-[#0d0d0d] p-4">
      <p className="text-xs font-medium uppercase tracking-[0.12em] text-gray-500">{label}</p>
      <p className={`mt-3 text-2xl font-semibold tabular-nums ${toneClass}`}>{value}</p>
      {detail ? <p className="mt-2 text-xs leading-5 text-gray-500">{detail}</p> : null}
    </div>
  );
}

function LoadingPanel() {
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="h-28 animate-pulse rounded-lg border border-gray-800 bg-gray-900" />
        ))}
      </div>
      <div className="h-48 animate-pulse rounded-lg border border-gray-800 bg-gray-900" />
    </div>
  );
}

export default function BacktestAlertsWorkspace() {
  const [backtestForm, setBacktestForm] = useState<BacktestFormState>(INITIAL_BACKTEST_FORM);
  const [backtestErrors, setBacktestErrors] = useState<FormErrors>({});
  const [backtestResult, setBacktestResult] = useState<BacktestRunResponse | null>(null);
  const [backtestLoading, setBacktestLoading] = useState(false);
  const [backtestError, setBacktestError] = useState<string | null>(null);

  const [alertForm, setAlertForm] = useState<AlertFormState>(INITIAL_ALERT_FORM);
  const [alertErrors, setAlertErrors] = useState<FormErrors>({});
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [events, setEvents] = useState<AlertEvent[]>([]);
  const [evaluation, setEvaluation] = useState<AlertEvaluationResponse | null>(null);
  const [alertsLoading, setAlertsLoading] = useState(true);
  const [alertMessage, setAlertMessage] = useState<string | null>(null);
  const [alertError, setAlertError] = useState<string | null>(null);
  const [submittingRule, setSubmittingRule] = useState(false);
  const [evaluatingRules, setEvaluatingRules] = useState(false);
  const [deletingRuleId, setDeletingRuleId] = useState<number | null>(null);
  const [togglingRuleId, setTogglingRuleId] = useState<number | null>(null);

  const refreshAlerts = useCallback(async () => {
    const [nextRules, nextEvents] = await Promise.all([
      fetchAlertRules(),
      fetchAlertEvents(),
    ]);
    setRules(nextRules);
    setEvents(nextEvents);
  }, []);

  useEffect(() => {
    let active = true;

    async function initializeAlerts() {
      try {
        const [nextRules, nextEvents] = await Promise.all([
          fetchAlertRules(),
          fetchAlertEvents(),
        ]);
        if (!active) {
          return;
        }
        setRules(nextRules);
        setEvents(nextEvents);
        setAlertError(null);
      } catch (error) {
        if (!active) {
          return;
        }
        setAlertError(getErrorMessage(error, "알림 규칙을 불러오지 못했습니다."));
      } finally {
        if (active) {
          setAlertsLoading(false);
        }
      }
    }

    void initializeAlerts();

    return () => {
      active = false;
    };
  }, [refreshAlerts]);

  const latestPendingByRuleId = useMemo(() => {
    const nextMap = new Map<number, AlertEvaluationResponse["pending_rules"][number]>();
    for (const pending of evaluation?.pending_rules ?? []) {
      nextMap.set(pending.rule_id, pending);
    }
    return nextMap;
  }, [evaluation]);

  async function handleBacktestSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextErrors = validateBacktestForm(backtestForm);
    setBacktestErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      return;
    }

    setBacktestLoading(true);
    setBacktestError(null);
    try {
      const result = await runBacktest({
        ticker: backtestForm.ticker.trim().toUpperCase(),
        strategy: "daily_recommendation_follow",
        start_date: backtestForm.startDate,
        end_date: backtestForm.endDate,
        initial_capital: Number(backtestForm.initialCapital.replaceAll(",", "")),
      });
      setBacktestResult(result);
    } catch (error) {
      setBacktestResult(null);
      setBacktestError(getErrorMessage(error, "백테스트를 실행하지 못했습니다."));
    } finally {
      setBacktestLoading(false);
    }
  }

  async function handleAlertCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextErrors = validateAlertForm(alertForm);
    setAlertErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      return;
    }

    setSubmittingRule(true);
    setAlertError(null);
    setAlertMessage(null);
    try {
      await createAlertRule({
        ticker: alertForm.ticker.trim().toUpperCase(),
        name: alertForm.name.trim(),
        rule_type: alertForm.ruleType,
        direction:
          alertForm.ruleType === "recommendation_change"
            ? null
            : alertForm.direction,
        threshold_value:
          alertForm.ruleType === "recommendation_change"
            ? null
            : Number(alertForm.thresholdValue),
        target_recommendation:
          alertForm.ruleType === "recommendation_change"
            ? alertForm.targetRecommendation
            : null,
        lookback_days:
          alertForm.ruleType === "sentiment_change"
            ? Number(alertForm.lookbackDays)
            : 2,
      });
      await refreshAlerts();
      setAlertForm({ ...INITIAL_ALERT_FORM, ticker: alertForm.ticker.trim().toUpperCase() || "005930" });
      setAlertMessage("알림 규칙을 저장했습니다.");
    } catch (error) {
      setAlertError(getErrorMessage(error, "알림 규칙을 저장하지 못했습니다."));
    } finally {
      setSubmittingRule(false);
    }
  }

  async function handleEvaluateRules() {
    setEvaluatingRules(true);
    setAlertError(null);
    setAlertMessage(null);
    try {
      const result = await evaluateAlertRules();
      setEvaluation(result);
      await refreshAlerts();
      setAlertMessage(
        result.triggered_count > 0
          ? `이번 평가에서 ${result.triggered_count}개의 이벤트가 발화됐습니다.`
          : "이번 평가에서는 새로 발화된 이벤트가 없었습니다.",
      );
    } catch (error) {
      setAlertError(getErrorMessage(error, "알림 규칙을 평가하지 못했습니다."));
    } finally {
      setEvaluatingRules(false);
    }
  }

  async function handleToggleRule(rule: AlertRule) {
    setTogglingRuleId(rule.id);
    setAlertError(null);
    setAlertMessage(null);
    try {
      await updateAlertRule(rule.id, { is_active: !rule.is_active });
      await refreshAlerts();
      setAlertMessage(rule.is_active ? "규칙을 비활성화했습니다." : "규칙을 다시 활성화했습니다.");
    } catch (error) {
      setAlertError(getErrorMessage(error, "규칙 상태를 바꾸지 못했습니다."));
    } finally {
      setTogglingRuleId(null);
    }
  }

  async function handleDeleteRule(ruleId: number) {
    setDeletingRuleId(ruleId);
    setAlertError(null);
    setAlertMessage(null);
    try {
      await deleteAlertRule(ruleId);
      await refreshAlerts();
      setEvaluation(null);
      setAlertMessage("규칙을 삭제했습니다.");
    } catch (error) {
      setAlertError(getErrorMessage(error, "규칙을 삭제하지 못했습니다."));
    } finally {
      setDeletingRuleId(null);
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">백테스트 · 개인 알림</h1>
        <p className="mt-1 text-sm text-gray-400">
          저장된 최종 일일 리포트와 가격·뉴스 데이터만으로 과거 시뮬레이션과 개인용 조건 알림을 관리합니다.
        </p>
      </div>

      <div className="rounded-lg border border-yellow-500/20 bg-yellow-500/5 px-4 py-3">
        <p className="text-sm text-yellow-300">
          여기의 백테스트는 과거 데이터를 단순화한 시뮬레이션이며, 실시간 추천·예측 진실·자동 매매 약속이 아닙니다.
        </p>
        <p className="mt-2 text-xs text-gray-500">
          알림도 저장된 종가·기술지표·감성·최종 일일 리포트만 평가합니다. 데이터가 없으면 기회가 없다는 뜻이 아니라 아직 평가할 근거가 부족하다는 뜻입니다.
        </p>
      </div>

      <SectionCard
        title="시뮬레이션 백테스트"
        description="현재는 `daily_recommendation_follow` 전략만 지원합니다. 최종 일일 리포트의 매수/매도 의견을 해당 날짜 종가에 체결된 것으로 단순화합니다."
      >
        <form className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_auto]" onSubmit={handleBacktestSubmit}>
          <label className="space-y-2">
            <span className="text-sm font-medium text-gray-300">티커</span>
            <input
              value={backtestForm.ticker}
              onChange={(event) => setBacktestForm((current) => ({ ...current, ticker: event.target.value.toUpperCase() }))}
              className="w-full rounded-lg border border-gray-800 bg-[#0d0d0d] px-3 py-2 text-sm text-white outline-none transition focus:border-sky-500/40"
              placeholder="005930"
            />
            {backtestErrors.ticker ? <p className="text-xs text-red-300">{backtestErrors.ticker}</p> : null}
          </label>

          <label className="space-y-2">
            <span className="text-sm font-medium text-gray-300">시작일</span>
            <input
              type="date"
              value={backtestForm.startDate}
              onChange={(event) => setBacktestForm((current) => ({ ...current, startDate: event.target.value }))}
              className="w-full rounded-lg border border-gray-800 bg-[#0d0d0d] px-3 py-2 text-sm text-white outline-none transition focus:border-sky-500/40"
            />
          </label>

          <label className="space-y-2">
            <span className="text-sm font-medium text-gray-300">종료일</span>
            <input
              type="date"
              value={backtestForm.endDate}
              onChange={(event) => setBacktestForm((current) => ({ ...current, endDate: event.target.value }))}
              className="w-full rounded-lg border border-gray-800 bg-[#0d0d0d] px-3 py-2 text-sm text-white outline-none transition focus:border-sky-500/40"
            />
          </label>

          <label className="space-y-2">
            <span className="text-sm font-medium text-gray-300">초기 자본</span>
            <input
              value={backtestForm.initialCapital}
              onChange={(event) => setBacktestForm((current) => ({ ...current, initialCapital: event.target.value }))}
              className="w-full rounded-lg border border-gray-800 bg-[#0d0d0d] px-3 py-2 text-sm text-white outline-none transition focus:border-sky-500/40"
              placeholder="100000"
              inputMode="decimal"
            />
            {backtestErrors.initialCapital ? <p className="text-xs text-red-300">{backtestErrors.initialCapital}</p> : null}
          </label>

          <button
            type="submit"
            disabled={backtestLoading}
            className="mt-7 inline-flex h-11 items-center justify-center rounded-lg border border-sky-500/30 px-4 text-sm font-medium text-sky-200 transition hover:bg-sky-500/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            {backtestLoading ? "계산 중..." : "시뮬레이션 실행"}
          </button>
        </form>

        {backtestError ? (
          <div className="mt-5 rounded-lg border border-red-500/20 bg-red-500/5 p-4 text-sm text-red-300">
            {backtestError}
          </div>
        ) : null}

        <div className="mt-6 rounded-lg border border-sky-500/20 bg-sky-500/5 px-4 py-3">
          <p className="text-sm text-sky-300">시뮬레이션 백테스트: 저장된 과거 데이터만으로 계산한 후행 분석입니다.</p>
          <p className="mt-1 text-xs text-gray-500">실거래 품질, 세금, 수수료, 미래 수익은 반영하지 않습니다.</p>
        </div>

        {backtestLoading ? (
          <div className="mt-6">
            <LoadingPanel />
          </div>
        ) : backtestResult ? (
          <div className="mt-6 space-y-6">
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <MetricCard label="총 수익률" value={formatPercent(backtestResult.summary.total_return_percent)} toneClass={getBacktestTone(backtestResult.summary.total_return_percent)} detail={`${backtestResult.summary.start_date} → ${backtestResult.summary.end_date}`} />
              <MetricCard label="종료 자본" value={formatNumber(backtestResult.summary.ending_capital)} detail={`초기 ${formatNumber(backtestResult.summary.initial_capital)} 기준`} />
              <MetricCard label="완결 거래" value={String(backtestResult.summary.completed_trades)} detail={`승 ${backtestResult.summary.wins} / 패 ${backtestResult.summary.losses}`} />
              <MetricCard label="타임라인 이벤트" value={String(backtestResult.summary.event_count)} detail={backtestResult.summary.open_position ? "열린 포지션 있음" : "기간 종료 시 포지션 없음"} />
            </div>

            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
              <section className="rounded-lg border border-gray-800 bg-[#0d0d0d] p-4">
                <h3 className="text-sm font-semibold text-white">시뮬레이션 타임라인</h3>
                <div className="mt-4 space-y-3">
                  {backtestResult.timeline.map((event) => (
                    <article key={`${event.trade_date}-${event.event_type}`} className="rounded-lg border border-gray-800 bg-[#111111] p-4">
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div>
                          <p className="text-sm font-semibold text-white">{event.trade_date} · {event.event_type === "buy" ? "진입" : event.event_type === "sell" ? "청산" : "기간 종료 청산"}</p>
                          <p className="mt-1 text-sm leading-6 text-gray-300">{event.message}</p>
                        </div>
                        <div className="rounded-lg border border-gray-700 bg-black/20 px-3 py-2 text-left sm:text-right">
                          <p className="text-xs font-medium uppercase tracking-[0.12em] text-gray-500">종가</p>
                          <p className="mt-1 text-lg font-semibold tabular-nums text-white">{formatNumber(event.price, 2)}</p>
                        </div>
                      </div>
                      <dl className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4 text-sm text-gray-300">
                        <div>
                          <dt className="text-gray-500">추천</dt>
                          <dd className="mt-1">{formatRecommendationLabel(event.recommendation)}</dd>
                        </div>
                        <div>
                          <dt className="text-gray-500">수량</dt>
                          <dd className="mt-1 tabular-nums">{formatNumber(event.shares, 2)}</dd>
                        </div>
                        <div>
                          <dt className="text-gray-500">현금 잔고</dt>
                          <dd className="mt-1 tabular-nums">{formatNumber(event.cash_balance, 2)}</dd>
                        </div>
                        <div>
                          <dt className="text-gray-500">실현 수익률</dt>
                          <dd className="mt-1 tabular-nums">{formatPercent(event.realized_return_percent ?? null)}</dd>
                        </div>
                      </dl>
                    </article>
                  ))}
                </div>
              </section>

              <section className="rounded-lg border border-gray-800 bg-[#0d0d0d] p-4">
                <h3 className="text-sm font-semibold text-white">가정과 한계</h3>
                <ul className="mt-3 space-y-2 text-sm leading-6 text-gray-300">
                  {backtestResult.assumptions.map((item) => (
                    <li key={item} className="flex gap-2">
                      <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-sky-400" />
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
                <div className="mt-5 rounded-lg border border-yellow-500/20 bg-yellow-500/5 p-4">
                  <p className="text-xs font-medium uppercase tracking-[0.12em] text-yellow-300">주의</p>
                  <ul className="mt-2 space-y-2 text-sm leading-6 text-gray-300">
                    {backtestResult.limitations.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              </section>
            </div>
          </div>
        ) : (
          <div className="mt-6 rounded-lg border border-gray-800 bg-[#0d0d0d] p-6">
            <p className="text-sm text-gray-300">아직 시뮬레이션 결과가 없습니다.</p>
            <p className="mt-2 text-xs text-gray-500">티커와 날짜 범위를 입력한 뒤 실행하면, 저장된 최종 일일 리포트 기준의 과거 체결 타임라인만 보여 줍니다. 미래를 예측하는 화면이 아닙니다.</p>
          </div>
        )}
      </SectionCard>

      <SectionCard
        title="개인용 조건 알림"
        description="목표가, RSI, 감성 변화, 최종 일일 추천 변화만 평가합니다. 조건이 충족되지 않으면 규칙은 대기 상태로 남고 이벤트를 만들지 않습니다."
        actions={
          <button
            type="button"
            onClick={handleEvaluateRules}
            disabled={evaluatingRules || alertsLoading}
            className="inline-flex items-center justify-center rounded-lg border border-sky-500/30 px-4 py-2 text-sm font-medium text-sky-200 transition hover:bg-sky-500/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            {evaluatingRules ? "평가 중..." : "지금 규칙 평가"}
          </button>
        }
      >
        <form className="grid gap-4 lg:grid-cols-2" onSubmit={handleAlertCreate}>
          <label className="space-y-2">
            <span className="text-sm font-medium text-gray-300">티커</span>
            <input
              value={alertForm.ticker}
              onChange={(event) => setAlertForm((current) => ({ ...current, ticker: event.target.value.toUpperCase() }))}
              className="w-full rounded-lg border border-gray-800 bg-[#0d0d0d] px-3 py-2 text-sm text-white outline-none transition focus:border-sky-500/40"
            />
            {alertErrors.ticker ? <p className="text-xs text-red-300">{alertErrors.ticker}</p> : null}
          </label>

          <label className="space-y-2">
            <span className="text-sm font-medium text-gray-300">규칙 이름</span>
            <input
              value={alertForm.name}
              onChange={(event) => setAlertForm((current) => ({ ...current, name: event.target.value }))}
              className="w-full rounded-lg border border-gray-800 bg-[#0d0d0d] px-3 py-2 text-sm text-white outline-none transition focus:border-sky-500/40"
              placeholder="예: 삼성전자 목표가 돌파"
            />
            {alertErrors.name ? <p className="text-xs text-red-300">{alertErrors.name}</p> : null}
          </label>

          <label className="space-y-2">
            <span className="text-sm font-medium text-gray-300">규칙 종류</span>
            <select
              value={alertForm.ruleType}
              onChange={(event) => {
                const ruleType = event.target.value as AlertFormState["ruleType"];
                setAlertForm((current) => ({
                  ...current,
                  ruleType,
                  direction: ruleType === "sentiment_change" ? "up" : "above",
                }));
              }}
              className="w-full rounded-lg border border-gray-800 bg-[#0d0d0d] px-3 py-2 text-sm text-white outline-none transition focus:border-sky-500/40"
            >
              <option value="target_price">목표가</option>
              <option value="rsi_threshold">RSI</option>
              <option value="sentiment_change">감성 변화</option>
              <option value="recommendation_change">추천 변화</option>
            </select>
          </label>

          {alertForm.ruleType === "recommendation_change" ? (
            <label className="space-y-2">
              <span className="text-sm font-medium text-gray-300">원하는 추천 상태</span>
              <select
                value={alertForm.targetRecommendation}
                onChange={(event) => setAlertForm((current) => ({ ...current, targetRecommendation: event.target.value }))}
                className="w-full rounded-lg border border-gray-800 bg-[#0d0d0d] px-3 py-2 text-sm text-white outline-none transition focus:border-sky-500/40"
              >
                <option value="buy">매수</option>
                <option value="hold">보유</option>
                <option value="sell">매도</option>
              </select>
            </label>
          ) : (
            <>
              <label className="space-y-2">
                <span className="text-sm font-medium text-gray-300">방향</span>
                <select
                  value={alertForm.direction}
                  onChange={(event) => setAlertForm((current) => ({ ...current, direction: event.target.value }))}
                  className="w-full rounded-lg border border-gray-800 bg-[#0d0d0d] px-3 py-2 text-sm text-white outline-none transition focus:border-sky-500/40"
                >
                  {alertForm.ruleType === "sentiment_change" ? (
                    <>
                      <option value="up">상승</option>
                      <option value="down">하락</option>
                    </>
                  ) : (
                    <>
                      <option value="above">이상</option>
                      <option value="below">이하</option>
                    </>
                  )}
                </select>
              </label>

              <label className="space-y-2">
                <span className="text-sm font-medium text-gray-300">임계값</span>
                <input
                  value={alertForm.thresholdValue}
                  onChange={(event) => setAlertForm((current) => ({ ...current, thresholdValue: event.target.value }))}
                  className="w-full rounded-lg border border-gray-800 bg-[#0d0d0d] px-3 py-2 text-sm text-white outline-none transition focus:border-sky-500/40"
                  placeholder={alertForm.ruleType === "rsi_threshold" ? "70" : alertForm.ruleType === "sentiment_change" ? "0.40" : "80000"}
                  inputMode="decimal"
                />
                {alertErrors.thresholdValue ? <p className="text-xs text-red-300">{alertErrors.thresholdValue}</p> : null}
              </label>
            </>
          )}

          {alertForm.ruleType === "sentiment_change" ? (
            <label className="space-y-2">
              <span className="text-sm font-medium text-gray-300">비교 기사 수</span>
              <input
                value={alertForm.lookbackDays}
                onChange={(event) => setAlertForm((current) => ({ ...current, lookbackDays: event.target.value }))}
                className="w-full rounded-lg border border-gray-800 bg-[#0d0d0d] px-3 py-2 text-sm text-white outline-none transition focus:border-sky-500/40"
                inputMode="numeric"
              />
              <p className="text-xs text-gray-500">최신 N건 평균과 직전 N건 평균을 비교합니다.</p>
            </label>
          ) : null}

          <div className="lg:col-span-2 flex flex-wrap items-center gap-3">
            <button
              type="submit"
              disabled={submittingRule}
              className="inline-flex items-center justify-center rounded-lg border border-sky-500/30 px-4 py-2 text-sm font-medium text-sky-200 transition hover:bg-sky-500/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submittingRule ? "저장 중..." : "알림 규칙 저장"}
            </button>
            <p className="text-xs text-gray-500">조건 미충족 시 이벤트를 만들지 않고 대기 상태만 유지합니다.</p>
          </div>
        </form>

        {alertMessage ? (
          <div className="mt-5 rounded-lg border border-green-500/20 bg-green-500/5 p-4 text-sm text-green-300">{alertMessage}</div>
        ) : null}
        {alertError ? (
          <div className="mt-5 rounded-lg border border-red-500/20 bg-red-500/5 p-4 text-sm text-red-300">{alertError}</div>
        ) : null}

        {alertsLoading ? (
          <div className="mt-6">
            <LoadingPanel />
          </div>
        ) : (
          <div className="mt-6 space-y-6">
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <MetricCard label="활성 규칙" value={String(rules.filter((rule) => rule.is_active).length)} detail={`${rules.length}개 중`} />
              <MetricCard label="최근 이벤트" value={String(events.length)} detail="저장된 발화 기록" />
              <MetricCard label="직전 평가 규칙 수" value={String(evaluation?.evaluated_count ?? 0)} detail={evaluation ? "최근 수동 평가 기준" : "아직 수동 평가 전"} />
              <MetricCard label="직전 신규 발화" value={String(evaluation?.triggered_count ?? 0)} detail="동일 상태 중복 이벤트는 억제" />
            </div>

            <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
              <section className="rounded-lg border border-gray-800 bg-[#0d0d0d] p-4">
                <h3 className="text-sm font-semibold text-white">규칙 목록</h3>
                {rules.length > 0 ? (
                  <div className="mt-4 space-y-3">
                    {rules.map((rule) => {
                      const pendingSummary = latestPendingByRuleId.get(rule.id);
                      return (
                        <article key={rule.id} className="rounded-lg border border-gray-800 bg-[#111111] p-4">
                          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                            <div>
                              <div className="flex flex-wrap items-center gap-2">
                                <h4 className="text-sm font-semibold text-white">{rule.name}</h4>
                                <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium ${rule.is_active ? "border-yellow-500/30 bg-yellow-500/10 text-yellow-300" : "border-gray-700 bg-gray-800 text-gray-300"}`}>
                                  {rule.is_active ? (pendingSummary ? "대기 중" : "활성") : "비활성"}
                                </span>
                              </div>
                              <p className="mt-1 text-sm text-gray-400">{rule.ticker} · {formatRuleType(rule.rule_type)}</p>
                              <p className="mt-2 text-xs leading-5 text-gray-500">
                                {rule.rule_type === "recommendation_change"
                                  ? `이전 최종 일일 추천과 비교해 ${formatRecommendationLabel(rule.target_recommendation)}로 바뀌면 발화합니다.`
                                  : `${formatDirection(rule.direction)} / ${rule.threshold_value ?? "-"}${rule.rule_type === "rsi_threshold" ? " RSI" : ""}`}
                              </p>
                              {pendingSummary ? (
                                <p className="mt-2 text-xs leading-5 text-yellow-200">{pendingSummary.message}</p>
                              ) : null}
                            </div>
                            <div className="flex gap-2">
                              <button
                                type="button"
                                onClick={() => void handleToggleRule(rule)}
                                disabled={togglingRuleId === rule.id}
                                className="rounded-lg border border-gray-700 px-3 py-2 text-xs font-medium text-gray-200 transition hover:border-sky-500/40 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
                              >
                                {togglingRuleId === rule.id ? "변경 중..." : rule.is_active ? "비활성화" : "재활성화"}
                              </button>
                              <button
                                type="button"
                                onClick={() => void handleDeleteRule(rule.id)}
                                disabled={deletingRuleId === rule.id}
                                className="rounded-lg border border-red-500/30 px-3 py-2 text-xs font-medium text-red-200 transition hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-60"
                              >
                                {deletingRuleId === rule.id ? "삭제 중..." : "삭제"}
                              </button>
                            </div>
                          </div>
                        </article>
                      );
                    })}
                  </div>
                ) : (
                  <div className="mt-4 rounded-lg border border-gray-800 bg-[#111111] p-5">
                    <p className="text-sm text-gray-300">아직 저장된 개인 알림 규칙이 없습니다.</p>
                    <p className="mt-2 text-xs text-gray-500">위 폼에서 규칙을 추가한 뒤 수동 평가를 실행하면 triggered/pending 상태를 정직하게 확인할 수 있습니다.</p>
                  </div>
                )}
              </section>

              <div className="space-y-4">
                <section className="rounded-lg border border-gray-800 bg-[#0d0d0d] p-4">
                  <h3 className="text-sm font-semibold text-white">이번 평가에서 대기 중인 규칙</h3>
                  {evaluation?.pending_rules && evaluation.pending_rules.length > 0 ? (
                    <div className="mt-4 space-y-3">
                      {evaluation.pending_rules.map((pending) => (
                        <article key={pending.rule_id} className="rounded-lg border border-yellow-500/20 bg-yellow-500/5 p-4">
                          <div className="flex items-center justify-between gap-3">
                            <p className="text-sm font-semibold text-yellow-200">{pending.ticker} · {formatRuleType(pending.rule_type)}</p>
                            <span className="text-xs font-medium text-yellow-300">대기</span>
                          </div>
                          <p className="mt-2 text-sm leading-6 text-gray-300">{pending.message}</p>
                          <dl className="mt-3 grid gap-3 sm:grid-cols-2 text-xs text-gray-400">
                            <div>
                              <dt>관측값</dt>
                              <dd className="mt-1 text-white">{pending.observed_text ?? formatNumber(pending.observed_value, 2)}</dd>
                            </div>
                            <div>
                              <dt>기준값</dt>
                              <dd className="mt-1 text-white">{pending.threshold_text ?? formatNumber(pending.threshold_value, 2)}</dd>
                            </div>
                          </dl>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <div className="mt-4 rounded-lg border border-gray-800 bg-[#111111] p-4 text-sm text-gray-300">
                      {evaluation
                        ? "직전 수동 평가에서는 대기 규칙이 없었거나, 새 규칙을 아직 다시 평가하지 않았습니다."
                        : "아직 수동 평가를 실행하지 않았습니다. 데이터를 모른 척하지 않기 위해 자동으로 pending을 지어내지 않습니다."}
                    </div>
                  )}
                </section>

                <section className="rounded-lg border border-gray-800 bg-[#0d0d0d] p-4">
                  <h3 className="text-sm font-semibold text-white">최근 발화 이벤트</h3>
                  {events.length > 0 ? (
                    <div className="mt-4 space-y-3">
                      {events.map((event) => (
                        <article key={event.id} className="rounded-lg border border-sky-500/20 bg-sky-500/5 p-4">
                          <div className="flex items-center justify-between gap-3">
                            <p className="text-sm font-semibold text-sky-200">{event.ticker} · {formatRuleType(event.rule_type)}</p>
                            <span className="text-xs font-medium text-sky-300">triggered</span>
                          </div>
                          <p className="mt-2 text-sm leading-6 text-gray-300">{event.message}</p>
                          <dl className="mt-3 grid gap-3 sm:grid-cols-2 text-xs text-gray-400">
                            <div>
                              <dt>관측 시점</dt>
                              <dd className="mt-1 text-white">{event.observed_at ?? "-"}</dd>
                            </div>
                            <div>
                              <dt>관측값</dt>
                              <dd className="mt-1 text-white">{event.observed_text ?? formatNumber(event.observed_value, 2)}</dd>
                            </div>
                            <div>
                              <dt>기준</dt>
                              <dd className="mt-1 text-white">{event.threshold_text ?? formatNumber(event.threshold_value, 2)}</dd>
                            </div>
                            <div>
                              <dt>이전 상태</dt>
                              <dd className="mt-1 text-white">{event.baseline_text ?? formatNumber(event.baseline_value, 2)}</dd>
                            </div>
                          </dl>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <div className="mt-4 rounded-lg border border-gray-800 bg-[#111111] p-4 text-sm text-gray-300">
                      아직 발화된 이벤트가 없습니다. 이는 안전 신호가 아니라, 현재 저장된 데이터 범위에서 아직 조건이 충족되지 않았다는 뜻일 수 있습니다.
                    </div>
                  )}
                </section>
              </div>
            </div>
          </div>
        )}
      </SectionCard>
    </div>
  );
}
