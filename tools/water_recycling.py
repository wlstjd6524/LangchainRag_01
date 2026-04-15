from langchain_core.tools import tool

@tool
def analyze_water_resource_circulation(
    industry: str,
    total_withdrawal: float,
    recycled_water: float,
    total_waste: float,
    recycled_waste: float
) -> str:
    """
    GRI 303(용수) 및 306(폐기물) 표준을 기반으로 기업의 자원 순환 지표를 산출하고 공시 현황을 분석함.
    """
    
    # 1. 지표 산출 로직
    # 용수 재활용률 = (재활용 용수량 / 총 취수량)
    water_rate = (recycled_water / total_withdrawal * 100) if total_withdrawal > 0 else 0
    # 자원 순환율 = (재활용 폐기물량 / 총 폐기물량)
    waste_rate = (recycled_waste / total_waste * 100) if total_waste > 0 else 0

    # 2. GRI 및 K-ESG 기반 정성적 상태 진단 (절대값 판단 지양)
    # 측정 및 공시 여부 자체가 관리 수준의 척도임
    def get_management_status(rate: float) -> str:
        if rate > 0:
            return "측정 및 관리 중 (공시 데이터 존재)"
        return "데이터 미확인 (공시 체계 점검 필요)"

    # 3. 최종 분석 리포트 생성
    report = [
        f"## 💧 ESG 자원 순환 분석 결과 ({industry})",
        "",
        "### 📊 핵심 성과 지표 (KPI)",
        f"| 항목 | 산출값 | 관리 상태 |",
        f"| :--- | :--- | :--- |",
        f"| **용수 재활용률** | `{water_rate:.2f}%` | {get_management_status(water_rate)} |",
        f"| **자원 순환율** | `{waste_rate:.2f}%` | {get_management_status(waste_rate)} |",
        "",
        "---",
        "### 💡 GRI 303/306 기반 전문가 제언",
        f"1. **공시 투명성:** 현재 {industry} 업종 내에서 해당 수치를 측정하고 있다는 점 자체가 GRI 303-1, 306-2 가이드라인에 부합하는 관리의 시작입니다.",
        f"2. **순환 경제 이행:** 단순 재활용률 수치보다 중요한 것은 '전년 대비 개선 추이'와 '재사용 프로세스의 구체성'입니다.",
        "3. **권고 사항:** 해당 지표를 지속가능경영보고서 내 정량 데이터로 포함시키고, 취수원 및 폐기물 처리 경로에 대한 상세 영향 분석(Impact Assessment)을 병행하십시오.",
        "",
        "⚠️ **주의:** 타사 대비 수준이나 업종별 가이드라인 대조가 필요할 경우 `search_esg_guideline` 도구를 추가로 호출하여 비교 분석하시기 바랍니다."
    ]

    return "\n".join(report)