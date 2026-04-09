# ESG 평가 도구 모음
# 각 팀원이 개발한 툴을 이 파일에 import해서 tools 리스트에 추가하세요.
#
# 예시:
# from .search_guideline import search_guideline
# from .calculate_carbon import calculate_carbon
#
# tools 리스트에 추가된 툴은 Agent가 자동으로 인식합니다.

from .calculate_demo import calculate_carbon_emission
from .search_pdf import search_pdf_tool  # ✅ 방금 개발한 RAG 검색 툴 임포트

# 에이전트에게 쥐어줄 무기(Tool) 리스트
tools = [
    calculate_carbon_emission,
    search_pdf_tool  # ✅ 리스트에 추가
]