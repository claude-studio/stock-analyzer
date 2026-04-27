const SERVER_API_URL = process.env.API_URL || "http://stock-api:8000";
const CLIENT_API_URL = process.env.NEXT_PUBLIC_API_URL || "";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

export class APIError extends Error {
  status: number;
  detail: string | null;

  constructor(status: number, detail?: string | null) {
    super(detail ?? `API Error: ${status}`);
    this.name = "APIError";
    this.status = status;
    this.detail = detail ?? null;
  }
}

function getBaseUrl(): string {
  if (typeof window === "undefined") {
    return SERVER_API_URL;
  }
  return CLIENT_API_URL;
}
export async function fetchAPI<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10_000);
  const abortFromOption = () => controller.abort(options?.signal?.reason);

  if (options?.signal?.aborted) {
    abortFromOption();
  } else {
    options?.signal?.addEventListener("abort", abortFromOption, { once: true });
  }

  try {
    const base = getBaseUrl();
    const res = await fetch(`${base}${path}`, {
      ...options,
      signal: controller.signal,
      headers: {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json",
        ...options?.headers,
      },
    });

    if (!res.ok) {
      let detail: string | null = null;

      try {
        const data = (await res.json()) as {
          detail?: string;
          message?: string;
          error?: string;
        };
        detail = data.detail ?? data.message ?? data.error ?? null;
      } catch {
        detail = null;
      }

      throw new APIError(res.status, detail);
    }

    return res.json();
  } finally {
    clearTimeout(timeout);
    options?.signal?.removeEventListener("abort", abortFromOption);
  }
}

export interface Stock {
  ticker: string;
  name: string;
  market: string;
  sector: string | null;
}

export interface DailyPrice {
  trade_date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface AnalysisReport {
  summary: string;
  recommendation: string;
  confidence: number | null;
  target_price: number | null;
  bull_case: string | null;
  bear_case: string | null;
  key_factors: string[] | Record<string, string> | null;
  analysis_date: string;
  analysis_type?: string;
  model_used?: string | null;
  created_at?: string | null;
}

export interface AnalysisHistoryItem extends AnalysisReport {
  analysis_type: string;
  model_used: string | null;
  created_at: string | null;
}

export interface AnalysisHistoryResponse {
  ticker: string;
  history: AnalysisHistoryItem[];
}

export interface StockDetailResponse {
  stock: Stock | null;
  prices: DailyPrice[];
  latest_price: DailyPrice | null;
  analysis: AnalysisReport | null;
  news: NewsArticle[];
  technical: TechnicalIndicators | null;
}

export interface AccuracyStats {
  total: number;
  hit_rate_7d: number;
  hit_rate_30d: number;
  by_recommendation: Record<
    string,
    { count: number; hit_rate_7d: number }
  >;
}

export interface MarketOverview {
  kospi: { value: number; change: number; change_pct: number };
  kosdaq: { value: number; change: number; change_pct: number };
}

export interface HealthStatus {
  status: string;
  scheduler_running: boolean;
}

export interface NewsArticle {
  id?: number;
  title: string;
  source: string;
  url: string | null;
  published_at: string;
  sentiment_score: number | null;
  sentiment_label: string | null;
  stock_ticker: string | null;
  stock_name: string | null;
  news_category?: string | null;
  impact_summary?: string | null;
  sector?: string | null;
  impact_score?: number | null;
  impacts?: NewsImpact[];
}

export interface NewsImpact {
  article_id?: number;
  title?: string | null;
  url?: string | null;
  stock_ticker: string;
  stock_name: string;
  impact_direction: string;
  impact_score: number | null;
  reason: string | null;
  published_at?: string | null;
  effective_trading_date?: string | null;
  window?: string | null;
  benchmark?: string | null;
  stock_return?: number | null;
  benchmark_return?: number | null;
  abnormal_return?: number | null;
  car?: number | null;
  observed_windows?: {
    window: string;
    benchmark: string | null;
    stock_return: number | null;
    benchmark_return: number | null;
    abnormal_return: number | null;
    car: number | null;
    confidence: number | null;
    data_status: string;
  }[];
  confidence?: number | null;
  confounded?: boolean;
  data_status?: string | null;
  marker_label?: string | null;
}

export interface NewsImpactSummaryItem {
  title: string;
  impact_direction: string;
  impact_score: number | null;
  reason: string | null;
  published_at: string | null;
  url: string | null;
}

export interface NewsImpactSummary {
  ticker: string;
  name?: string;
  total_count: number;
  total_news?: number;
  bullish_count: number;
  bearish_count: number;
  neutral_count: number;
  avg_impact_score: number;
  recent_impacts: NewsImpact[];
  event_markers?: NewsImpact[];
}

export interface TechnicalIndicators {
  rsi_14: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_hist: number | null;
  sma_5: number | null;
  sma_20: number | null;
  sma_60: number | null;
  bb_upper: number | null;
  bb_middle: number | null;
  bb_lower: number | null;
  atr_14: number | null;
  price_position: string | null;
  trend: string | null;
}

export interface WatchlistItem {
  ticker: string;
  name: string;
  close: number | null;
  change_pct: number | null;
  volume: number | null;
  recommendation: string | null;
  analysis_date: string | null;
}

export interface PortfolioHolding {
  id: number;
  ticker: string;
  name: string;
  market: string;
  currency: string;
  quantity: number;
  average_price: number;
  invested_amount: number;
  latest_trade_date: string | null;
  latest_price: number | null;
  latest_valuation: number | null;
  unrealized_pnl: number | null;
  unrealized_pnl_percent: number | null;
  allocation_percent: number | null;
  is_price_missing: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface PortfolioAllocationItem {
  holding_id: number;
  ticker: string;
  name: string;
  market: string;
  currency: string;
  latest_valuation: number | null;
  allocation_percent: number | null;
  is_price_missing: boolean;
}

export interface PortfolioCurrencyBreakdown {
  currency: string;
  invested_amount: number;
  latest_valuation: number | null;
  unrealized_pnl: number | null;
  unrealized_pnl_percent: number | null;
  has_missing_prices: boolean;
}

export interface PortfolioSummary {
  invested_amount: number | null;
  latest_valuation: number | null;
  unrealized_pnl: number | null;
  unrealized_pnl_percent: number | null;
  has_missing_prices: boolean;
  has_mixed_currencies: boolean;
  currency_breakdown: PortfolioCurrencyBreakdown[];
  holdings: PortfolioHolding[];
  allocation: PortfolioAllocationItem[];
}

export interface PortfolioHoldingCreatePayload {
  ticker: string;
  quantity: number;
  average_price: number;
}

export interface PortfolioHoldingUpdatePayload {
  ticker?: string;
  quantity?: number;
  average_price?: number;
}

export interface ScreenerCoverage {
  ranked_markets: string[];
  excluded_markets: string[];
  uses_stored_data_only: boolean;
  eligible_stocks: number;
  insufficient_stocks: number;
}

export interface ScreenerEmptyState {
  title: string;
  description: string;
}

export interface ScreenerComponents {
  price_momentum_pct: number | null;
  price_momentum_score: number | null;
  volume_spike_ratio: number | null;
  volume_spike_score: number | null;
  recent_news_count: number;
  recent_news_score: number | null;
  avg_news_impact_score: number | null;
  news_impact_score: number | null;
  latest_daily_recommendation: string | null;
  latest_daily_recommendation_score: number | null;
}

export interface ScreenerCandidate {
  ticker: string;
  name: string;
  market: string;
  sector: string | null;
  score: number;
  components: ScreenerComponents;
  reasons: string[];
  latest_recommendation: string | null;
  analysis_date: string | null;
  latest_close: number | null;
  latest_trade_date: string | null;
}

export interface ScreenerResponse {
  candidates: ScreenerCandidate[];
  total_candidates: number;
  total_eligible: number;
  total_insufficient: number;
  limit: number;
  lookback_days: number;
  news_window_days: number;
  minimum_price_points: number;
  reference_trade_date: string | null;
  generated_at: string;
  coverage: ScreenerCoverage;
  limitations: string[];
  empty_state: ScreenerEmptyState;
}

export interface BacktestSummary {
  start_date: string;
  end_date: string;
  initial_capital: number;
  ending_capital: number;
  total_return_percent: number;
  completed_trades: number;
  wins: number;
  losses: number;
  open_position: boolean;
  event_count: number;
}

export interface BacktestTimelineEvent {
  trade_date: string;
  event_type: string;
  price: number;
  recommendation: string | null;
  shares: number;
  cash_balance: number;
  position_value: number;
  realized_return_percent?: number | null;
  message: string;
}

export interface BacktestRunResponse {
  ticker: string;
  name: string;
  strategy: string;
  generated_at: string;
  assumptions: string[];
  limitations: string[];
  summary: BacktestSummary;
  timeline: BacktestTimelineEvent[];
}

export interface BacktestRunPayload {
  ticker: string;
  strategy: "daily_recommendation_follow";
  start_date: string;
  end_date: string;
  initial_capital: number;
}

export interface AlertRule {
  id: number;
  ticker: string | null;
  name: string;
  rule_type: string;
  direction: string | null;
  threshold_value: number | null;
  target_recommendation: string | null;
  lookback_days: number;
  is_active: boolean;
  last_evaluated_at: string | null;
  last_triggered_at: string | null;
}

export interface AlertRulePayload {
  ticker: string;
  name: string;
  rule_type: "target_price" | "rsi_threshold" | "sentiment_change" | "recommendation_change";
  direction?: string | null;
  threshold_value?: number | null;
  target_recommendation?: string | null;
  lookback_days?: number;
}

export interface AlertRuleUpdatePayload {
  name?: string;
  direction?: string | null;
  threshold_value?: number | null;
  target_recommendation?: string | null;
  lookback_days?: number;
  is_active?: boolean;
}

export interface AlertEvent {
  id: number;
  rule_id: number;
  ticker: string | null;
  rule_type: string;
  status: string;
  observed_value: number | null;
  observed_text: string | null;
  baseline_value: number | null;
  baseline_text: string | null;
  threshold_value: number | null;
  threshold_text: string | null;
  observed_at: string | null;
  message: string;
  created_at: string | null;
}

export interface AlertEvaluationSummary {
  rule_id: number;
  ticker: string;
  rule_type: string;
  status: string;
  observed_value: number | null;
  observed_text: string | null;
  baseline_value: number | null;
  baseline_text: string | null;
  threshold_value: number | null;
  threshold_text: string | null;
  observed_at: string | null;
  message: string;
}

export interface AlertEvaluationResponse {
  evaluated_count: number;
  triggered_count: number;
  triggered_events: AlertEvent[];
  pending_rules: AlertEvaluationSummary[];
}

export async function fetchNewsDetail(
  newsId: number,
): Promise<NewsArticle> {
  return fetchAPI<NewsArticle>(`/api/v1/news/${newsId}`);
}

export async function fetchNewsImpactSummary(
  ticker: string,
  days: number = 7,
): Promise<NewsImpactSummary> {
  return fetchAPI<NewsImpactSummary>(
    `/api/v1/stocks/${ticker}/news-impact?days=${days}`,
  );
}

export async function fetchAnalysisHistory(
  ticker: string,
): Promise<AnalysisHistoryResponse> {
  return fetchAPI<AnalysisHistoryResponse>(
    `/api/v1/stocks/${ticker}/analysis/history`,
  );
}

export async function fetchPortfolioSummary(): Promise<PortfolioSummary> {
  return fetchAPI<PortfolioSummary>("/api/v1/portfolio/summary");
}

export async function fetchPersonalScreener(
  limit: number = 10,
  lookbackDays: number = 30,
): Promise<ScreenerResponse> {
  return fetchAPI<ScreenerResponse>(
    `/api/v1/screener?limit=${limit}&lookback_days=${lookbackDays}`,
  );
}

export async function runBacktest(
  payload: BacktestRunPayload,
): Promise<BacktestRunResponse> {
  return fetchAPI<BacktestRunResponse>("/api/v1/backtests/run", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchAlertRules(): Promise<AlertRule[]> {
  return fetchAPI<AlertRule[]>("/api/v1/alerts/rules");
}

export async function createAlertRule(
  payload: AlertRulePayload,
): Promise<AlertRule> {
  return fetchAPI<AlertRule>("/api/v1/alerts/rules", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateAlertRule(
  ruleId: number,
  payload: AlertRuleUpdatePayload,
): Promise<AlertRule> {
  return fetchAPI<AlertRule>(`/api/v1/alerts/rules/${ruleId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deleteAlertRule(
  ruleId: number,
): Promise<{ deleted: boolean; rule_id: number }> {
  return fetchAPI<{ deleted: boolean; rule_id: number }>(`/api/v1/alerts/rules/${ruleId}`, {
    method: "DELETE",
  });
}

export async function fetchAlertEvents(limit: number = 20): Promise<AlertEvent[]> {
  return fetchAPI<AlertEvent[]>(`/api/v1/alerts/events?limit=${limit}`);
}

export async function evaluateAlertRules(): Promise<AlertEvaluationResponse> {
  return fetchAPI<AlertEvaluationResponse>("/api/v1/alerts/evaluate", {
    method: "POST",
  });
}

export async function createPortfolioHolding(
  payload: PortfolioHoldingCreatePayload,
): Promise<PortfolioHolding> {
  return fetchAPI<PortfolioHolding>("/api/v1/portfolio/holdings", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updatePortfolioHolding(
  holdingId: number,
  payload: PortfolioHoldingUpdatePayload,
): Promise<PortfolioHolding> {
  return fetchAPI<PortfolioHolding>(`/api/v1/portfolio/holdings/${holdingId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deletePortfolioHolding(
  holdingId: number,
): Promise<{ deleted: boolean; holding_id: number }> {
  return fetchAPI<{ deleted: boolean; holding_id: number }>(
    `/api/v1/portfolio/holdings/${holdingId}`,
    {
      method: "DELETE",
    },
  );
}
