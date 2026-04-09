# 1. 각 파일에서 실제 정의된 함수 이름을 정확히 임포트합니다.
from .calculate_demo import calculate_carbon_emission
from .web_search import web_search_esg
from .water_recycling import analyze_water_resource_circulation
from .search_PDF import search_pdf_tool  # 아연님의 RAG 도구 추가

# 2. 에이전트가 인식할 도구 리스트 정의
# nodes.py에서 이 리스트를 가져가서 LLM에게 바인딩합니다.
tools = [
    calculate_carbon_emission,
    web_search_esg,
    analyze_water_resource_circulation,
    search_pdf_tool
]

# 3. 패키지 외부 노출 설정
__all__ = [
    "tools", 
    "calculate_carbon_emission", 
    "web_search_esg", 
    "analyze_water_resource_circulation",
    "search_pdf_tool"
]