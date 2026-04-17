type Recommendation = "strong_buy" | "buy" | "hold" | "sell" | "strong_sell";

const BADGE_COLORS: Record<Recommendation, string> = {
  strong_buy: "bg-green-600 text-white",
  buy: "bg-green-500/20 text-green-400 border border-green-500/30",
  hold: "bg-yellow-500/20 text-yellow-400 border border-yellow-500/30",
  sell: "bg-red-500/20 text-red-400 border border-red-500/30",
  strong_sell: "bg-red-600 text-white",
};

const BADGE_LABELS: Record<Recommendation, string> = {
  strong_buy: "강력 매수",
  buy: "매수",
  hold: "보유",
  sell: "매도",
  strong_sell: "강력 매도",
};

interface BadgeProps {
  recommendation: Recommendation;
  className?: string;
}

export function Badge({ recommendation, className }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-medium ${BADGE_COLORS[recommendation]} ${className || ""}`}
    >
      {BADGE_LABELS[recommendation]}
    </span>
  );
}
