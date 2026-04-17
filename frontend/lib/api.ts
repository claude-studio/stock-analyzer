const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

export async function fetchAPI<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
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
