import { fetchAPI } from "@/lib/api";
import type { AccuracyStats } from "@/lib/api";

async function getAccuracy() {
  try {
    return await fetchAPI<AccuracyStats>("/api/v1/accuracy");
  } catch {
    return null;
  }
}

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-gray-800 bg-[#111111] p-5">
      <p className="text-sm font-medium text-gray-400">{label}</p>
      <p className="mt-2 text-3xl font-semibold tabular-nums">{value}</p>
      {sub && <p className="mt-1 text-xs text-gray-500">{sub}</p>}
    </div>
  );
}

export default async function AccuracyPage() {
  const stats = await getAccuracy();

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">적중률</h1>
        <p className="mt-1 text-sm text-gray-400">AI 분석의 방향성 예측 정확도</p>
      </div>

      {/* 면책 배너 */}
      <div className="rounded-lg border border-yellow-500/20 bg-yellow-500/5 px-4 py-3">
        <p className="text-sm text-yellow-400">
          적중률은 과거 분석 결과의 통계이며, 미래 수익을 보장하지 않습니다. 투자 판단은 본인 책임입니다.
        </p>
      </div>

      {stats ? (
        <>
          {/* 전체 통계 카드 */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <StatCard
              label="총 분석 건수"
              value={stats.total.toLocaleString("ko-KR")}
            />
            <StatCard
              label="7일 적중률"
              value={`${(stats.hit_rate_7d * 100).toFixed(1)}%`}
              sub="분석 후 7일 내 방향 일치"
            />
            <StatCard
              label="30일 적중률"
              value={`${(stats.hit_rate_30d * 100).toFixed(1)}%`}
              sub="분석 후 30일 내 방향 일치"
            />
          </div>

          {/* 추천별 적중률 */}
          <div>
            <h2 className="text-lg font-semibold mb-4">추천 유형별 적중률</h2>
            <div className="overflow-x-auto rounded-lg border border-gray-800">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-800 bg-[#0d0d0d]">
                    <th className="px-4 py-3 text-left font-medium text-gray-400">추천</th>
                    <th className="px-4 py-3 text-right font-medium text-gray-400">건수</th>
                    <th className="px-4 py-3 text-right font-medium text-gray-400">7일 적중률</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(stats.by_recommendation).map(([rec, data]) => (
                    <tr key={rec} className="border-b border-gray-800/50">
                      <td className="px-4 py-3 font-medium text-white">{rec}</td>
                      <td className="px-4 py-3 text-right tabular-nums text-gray-300">
                        {data.count.toLocaleString("ko-KR")}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">
                        <span
                          className={
                            data.hit_rate_7d >= 0.6
                              ? "text-green-400"
                              : data.hit_rate_7d >= 0.4
                                ? "text-yellow-400"
                                : "text-red-400"
                          }
                        >
                          {(data.hit_rate_7d * 100).toFixed(1)}%
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : (
        <div className="rounded-lg border border-gray-800 bg-[#111111] p-6">
          <p className="text-sm text-gray-400">적중률 데이터를 불러올 수 없습니다.</p>
          <p className="mt-1 text-xs text-gray-500">API 서버가 실행 중이고 충분한 분석 이력이 있는지 확인하세요.</p>
        </div>
      )}
    </div>
  );
}
