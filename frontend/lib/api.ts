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

export async function fetchPortfolioSummary(): Promise<PortfolioSummary> {
  return fetchAPI<PortfolioSummary>("/api/v1/portfolio/summary");
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
