import os
from dotenv import load_dotenv
from langchain_tavily import TavilySearch
from langchain_core.tools import tool


def _build_tavily_client() -> TavilySearch:
    load_dotenv()
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise EnvironmentError("TAVILY_API_KEY 환경 변수가 설정되어 있지 않습니다.")
    return TavilySearch(
        api_key=api_key,
        max_results=5,
        search_depth="advanced",
        include_answer=True,
    )

def _format_results(response, max_results: int = 5) -> str:
    """
    TavilySearch의 응답을 마크다운 형식으로 포맷팅한다.
    trust_flag 적용을 위해 URL을 '출처:' prefix 형태로 포함한다.
    """
    results = response.get("results", []) if isinstance(response, dict) else response
    if not results:
        return "검색 결과가 없습니다."
    
    formatted = []
    for i, r in enumerate(results[:max_results], 1):
        formatted.append(
            f"### 결과 {i}\n\n"
            f"**제목**: {r.get('title', 'N/A')}\n\n"
            f"**요약**: {r.get('content', 'N/A')}\n\n"
            f"**출처**: {r.get('url', 'N/A')}\n\n"
            f"---\n"
        )
    return "\n\n".join(formatted)
    
# 데이터 출처 추적
TRUSTED_DOMAINS = ["law.go.kr", "moel.go.kr", "fsc.go.kr", "dart.fss.or.kr"]

def _trust_flag(url: str) -> str:
    for domain in TRUSTED_DOMAINS:
        if domain in url:
            return "공식 출처"
    return "미공식 출처"


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
        검색 결과 마크다운 문자열 (출처 URL, 요약 내용, trust_flag 포함)
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
  
    # 검색 실행 및 출처 파싱
    try:
        print(f"##### ESG REGULATION SEARCH TOOL #####")
        print(f"##### Query: {query} #####")

        client = _build_tavily_client()
        response = client.invoke(query)
        raw_results = _format_results(response)

        # trust_flag 적용: '출처: URL' 패턴 탐자
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

    except EnvironmentError as e:
        return f"⚠️ 환경 설정 오류: {str(e)}"
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
