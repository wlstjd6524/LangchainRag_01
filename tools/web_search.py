"""
web_search_tool.py
ESG 에이전트용 웹서치 툴

설치:
  pip install langchain-tavily python-dotenv
"""

from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_tavily import TavilySearch

load_dotenv()

tavily_client = TavilySearch(
    max_results=5,
    search_depth="advanced",
    include_answer=True,
    include_raw_content=False,
)


@tool
def web_search_esg(query: str, max_results: int = 5) -> str:
    """
    ESG 관련 최신 정보를 웹에서 검색할 때 호출한다.
    kWh 숫자 계산이 아닌, 정보 조회·검색이 필요한 모든 경우에 사용한다.

    Args:
        query: 검색할 자연어 쿼리 (예: "2025 K-ESG 가이드라인 개정")
        max_results: 반환할 결과 수 (기본 5)

    Returns:
        검색 결과 요약 문자열 (출처 URL 포함)
    """
    try:
        print("##### WEB_SEARCH TOOL #####")
        print(f"##### Query : {query} #####")
        response = tavily_client.invoke(query)

        # langchain-tavily 버전에 따라 dict 또는 list로 반환됨
        if isinstance(response, dict):
            results = response.get("results", [])
        else:
            results = response

        if not results:
            return "검색 결과가 없습니다."

        formatted = []
        for i, r in enumerate(results[:max_results], 1):
            formatted.append(
                f"[{i}] {r.get('title', '제목 없음')}\n"
                f"    출처: {r.get('url', '')}\n"
                f"    요약: {r.get('content', '')[:300]}..."
            )

        return "\n\n".join(formatted)

    except Exception as e:
        return f"검색 오류: {str(e)}"


if __name__ == "__main__":
    result = web_search_esg.invoke({"query": "2025 K-ESG 가이드라인 개정"})
    print("=== 검색 결과 ===")
    print(result)
