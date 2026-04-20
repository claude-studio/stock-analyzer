const SERVER_API_URL = process.env.API_URL || "http://stock-api:8000";
const CLIENT_API_URL = process.env.NEXT_PUBLIC_API_URL || "";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

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
  const base = getBaseUrl();
  const res = await fetch(`${base}${path}`, {
    ...options,
    headers: {
      "X-API-Key": API_KEY,
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!res.ok) throw new Error(`API Error: ${res.status}`);
  return res.json();
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
  confidence: number;
  target_price: number | null;
  bull_case: string | null;
  bear_case: string | null;
  key_factors: string[];
  analysis_date: string;
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
  stock_ticker: string;
  stock_name: string;
  impact_direction: string;
  impact_score: number | null;
  reason: string | null;
}

export interface NewsImpactSummary {
  ticker: string;
  total_news: number;
  bullish_count: number;
  bearish_count: number;
  neutral_count: number;
  avg_impact_score: number;
  recent_impacts: {
    title: string;
    impact_direction: string;
    reason: string;
    published_at: string;
  }[];
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
