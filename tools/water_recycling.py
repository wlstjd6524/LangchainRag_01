# tools/water_recycling.py
from langchain_core.tools import tool
# RAG 도구를 가져옵니다. (상대 경로 임포트)
from .search_PDF import search_pdf_tool

@tool
def analyze_water_resource_circulation(
    industry: str,
    total_withdrawal: float,
    recycled_water: float,
    total_waste: float,
    recycled_waste: float
) -> str:
    """
    기업의 용수 이용 효율 및 자원 순환율을 분석하고 RAG를 통해 가이드라인을 조회합니다.
    """
    
    print(f"##### [TOOL] ANALYZING WATER & RESOURCE: {industry} #####")

    # 1. 산술 계산 로직
    # 용수 재활용률(%) = (재활용 용수량 / 총 취수량) * 100
    water_rate = (recycled_water / total_withdrawal) * 100 if total_withdrawal > 0 else 0
    # 자원 순환율(%) = (재활용 폐기물량 / 총 폐기물량) * 100
    waste_rate = (recycled_waste / total_waste) * 100 if total_waste > 0 else 0

    # 2. RAG 도구 호출 (K-ESG 가이드라인 기반)
    rag_query = f"{industry} 업종의 용수 재활용 및 자원 순환 평가지표 평균"
    
    try:
        rag_context = search_pdf_tool.invoke({
            "query": rag_query,
            "year": "공통",
            "doc_category": "K-ESG가이드라인"
        })
    except Exception as e:
        rag_context = f"⚠️ RAG 검색 중 오류가 발생했습니다: {str(e)}"

    # 3. 최종 분석 리포트 생성
    report = (
        f"## 💧 ESG 자원 순환 분석 리포트 ({industry})\n\n"
        f"### 📊 분석 결과\n"
        f"* **용수 재활용률:** `{water_rate:.2f}%` (재활용 {recycled_water} / 취수 {total_withdrawal})\n"
        f"* **자원 순환율:** `{waste_rate:.2f}%` (재활용 {recycled_waste} / 발생 {total_waste})\n\n"
        f"--- \n"
        f"### 📚 K-ESG 가이드라인 검색 결과\n"
        f"{rag_context}\n\n"
        f"--- \n"
        f"### 💡 전문가 제언\n"
        f"입력하신 **{industry}** 산업군의 가이드라인과 비교했을 때, "
        f"{'현재 자원 순환 시스템이 안정적으로 운영되고 있습니다.' if waste_rate > 50 else '폐기물 재활용 비중을 높이기 위한 프로세스 점검이 권고됩니다.'}"
    )

    return report