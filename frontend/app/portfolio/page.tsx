export default function PortfolioPage() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">포트폴리오</h1>
        <p className="mt-1 text-sm text-gray-400">보유 종목 관리 및 수익률 추적</p>
      </div>

      <div className="rounded-lg border border-gray-800 bg-[#111111] p-8 text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-gray-800">
          <svg
            className="h-6 w-6 text-gray-400"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1.5}
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
            />
          </svg>
        </div>
        <h2 className="text-lg font-semibold text-white">준비 중입니다</h2>
        <p className="mt-2 text-sm text-gray-400">
          포트폴리오 기능은 현재 개발 중입니다.
        </p>
        <div className="mt-6 rounded-lg border border-gray-800 bg-[#0d0d0d] p-4 text-left">
          <p className="text-sm font-medium text-gray-300 mb-2">향후 지원 예정 기능</p>
          <ul className="space-y-1.5 text-sm text-gray-500">
            <li className="flex items-center gap-2">
              <span className="h-1 w-1 rounded-full bg-gray-600" />
              보유 종목 등록 및 매수가 관리
            </li>
            <li className="flex items-center gap-2">
              <span className="h-1 w-1 rounded-full bg-gray-600" />
              실시간 수익률 계산
            </li>
            <li className="flex items-center gap-2">
              <span className="h-1 w-1 rounded-full bg-gray-600" />
              자산 배분 시각화
            </li>
            <li className="flex items-center gap-2">
              <span className="h-1 w-1 rounded-full bg-gray-600" />
              AI 리밸런싱 제안
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}
