from langchain_core.tools import tool
from .web_search import web_search_esg

@tool
def search_esg_regulation(
    topic: str,
    regulation_type: str = "all",
    year_filter: str = "",
) -> str:
    """
    ESG 지배구조(G) 관련 최신 법령·규제·뉴스를 웹에서 검색한다.
    사용자가 특정 법률, 공시 의무, 규제 동향을 질문할 때 호출한다.
    
    Args:
        topic: 검색할 규제/법령 주제(예: "이사회 독립성", ESG 공시 의무", "탄소 배출 규제")
        regulation_type: 검색 범위 필터.
            - "law": 법률·시행령·시행규칙 등 공식 법령
            - "guideline": K-ESG, GRI 등 가이드라인
            - "news": 최신 뉴스 기사·동향
            - "all": 전체 검색(기본값)
        year_filter: 특정 연도 필터 (예: "2025"). 빈 문자열이면 전체 기간.

    Returns:
        검색 결과 마크다운 문자열 (출처 URL, 요약 내용 포함)
    """

    # regulation_type에 따라 쿼리 접두어 결정
    PREFIX_MAP = {
        "law": "법령 시행령 규정",
        "guideline": "K-ESG GRI 가이드라인",
        "news": "최신 뉴스 동향",
        "all": "ESG 지배구조",
    }
    prefix = PREFIX_MAP.get(regulation_type, "ESG 지배구조")

    # 연도 필터 결합
    year_str = f"{year_filter}년 " if year_filter else ""

    # 최종 쿼리 생성
    query = f"{year_str}{prefix} {topic}"

    # 데이터 출처 추적
    TRUSTED_DOMAINS = ["law.go.kr", "moel.go.kr", "fsc.go.kr", "dart.fss.or.kr"]

    def _trust_flag(url: str) -> str:
        for domain in TRUSTED_DOMAINS:
            if domain in url:
                return "공식 출처"
        return "미공식 출처"
    
    # 검색 실행 및 출처 파싱
    try:
        print(f"##### ESG REGULATION SEARCH TOOL #####")
        print(f"##### Query: {query} #####")
        raw_results = web_search_esg.invoke({"query": query})

        lines = raw_results.splitlines()
        flagged_lines = []
        for line in lines:
            if line.strip().startswith("출처:"):
                url = line.strip().replace("출처:", "").strip()
                flag = _trust_flag(url)
                flagged_lines.append(f"{flag} | 출처: {url}")
            else:
                flagged_lines.append(line)
    
        result_with_flags = "\n".join(flagged_lines)

    except Exception as e:
        return f"⚠️ 검색 오류: {str(e)}"

    return (
        f"## ESG 법령·규제 검색 결과\n\n"
        f"**검색어**: {query}\n\n"
        f"---\n\n"
        f"{result_with_flags}\n\n"
        f"---\n"
        f"> ⚠️ 주의: 검색 결과는 최신 웹 정보를 기반으로 하며, 공식 출처 여부를 반드시 확인하세요."
    )
