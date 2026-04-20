"""멀티 분석가 구성 레지스트리."""

ANALYST_CONFIG: dict[str, dict] = {
    "value": {
        "name": "가치 분석가",
        "focus": "PER, PBR, ROE, 재무제표, 내재가치 대비 현재 주가 괴리",
        "system_prompt_addon": (
            "당신은 가치 투자 전문가입니다. "
            "재무제표와 밸류에이션 지표를 최우선으로 분석하세요."
        ),
        "weight": 0.35,
    },
    "momentum": {
        "name": "모멘텀 분석가",
        "focus": "RSI, MACD, 볼린저밴드, 거래량, 추세 전환 시그널",
        "system_prompt_addon": (
            "당신은 기술적 분석 전문가입니다. "
            "가격 패턴과 기술적 지표를 최우선으로 분석하세요."
        ),
        "weight": 0.35,
    },
    "sentiment": {
        "name": "감성 분석가",
        "focus": "뉴스 감성, 시장 심리, 수급 동향, 외국인/기관 매매 패턴",
        "system_prompt_addon": (
            "당신은 시장 심리 분석 전문가입니다. "
            "뉴스 감성과 수급 데이터를 최우선으로 분석하세요."
        ),
        "weight": 0.30,
    },
}
