# ESG 평가 도구 모음
# 각 팀원이 개발한 툴을 이 파일에 import해서 tools 리스트에 추가하세요.

from .calculate_carbon import calculate_carbon_emission
from .search_pdf import search_pdf_tool
from .web_search import web_search_esg
from .water_recycling import analyze_water_resource_circulation
from .calculate_safety import calculate_safety
from .calculate_employee_kpi import calculate_employee_kpi
from .search_esg_regulation import search_esg_regulation
from .score_ethics_risk import score_ethics_risk
from .csv_loader import load_csv_data
from .search_csv import search_emission_factor
from .report_generator import generate_report

# 에이전트가 인식할 도구 리스트 정의
tools = [
    calculate_carbon_emission,
    search_pdf_tool,
    web_search_esg,
    analyze_water_resource_circulation,
    calculate_safety,
    calculate_employee_kpi,
    search_esg_regulation,
    score_ethics_risk,
    load_csv_data,
    search_emission_factor,
    generate_report,
]

# 패키지 외부 노출 설정
__all__ = ["tools"]