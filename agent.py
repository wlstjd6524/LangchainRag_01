import pickle
import os
import time
from collections import defaultdict
from langchain_upstage import ChatUpstage
from langgraph.prebuilt import create_react_agent
from tools import tools
from middleware.logger import LoggingCallbackHandler, log_request, log_response

# 전역 설정
VECTORSTORE_DIR = "./vectorstore"
BM25_CACHE_FILE = os.path.join(VECTORSTORE_DIR, "bm25_docs.pkl")

def build_system_prompt() -> str:
    """
    BM25 캐시에서 메타데이터를 읽어 보유 문서 목록을 자동 생성합니다.
    파일이 추가/삭제되어도 ingest.py 재실행 후 자동으로 반영됩니다.
    """
    base_prompt = """당신은 ESG 공시 전문 가이드 에이전트입니다.
기업의 ESG(환경·사회·지배구조) 공시 관련 질문에 답변하고, 보고서 작성을 지원합니다.

## 보유 데이터베이스
search_esg_guideline 도구로 아래 문서들을 검색할 수 있습니다.

{doc_list}

[doc_category 파라미터] — 파일명의 세 번째 구분자 이후를 붙인 값:
{category_list}
주의: doc_category는 위 목록에 있는 값만 사용하세요.

### 탄소 배출계수 DB (search_emission_factor)
아래 3가지 유형의 배출계수를 조회할 수 있습니다:
  - korea_lci     : 국내 LCI 기반 품목별 배출계수 (원자재, 에너지, 건축자재 등)
  - defra_scope3  : DEFRA 기반 출장·운송 배출계수 (항공, 차량, 선박 등)
  - epa_spend     : EPA 기반 구매 지출 배출계수 (산업별 1만원/USD당 CO2e)

## 도구 선택 기준
| 질문 유형 | 사용 도구 |
|-----------|-----------|
| ESG 정책, 가이드라인, 보고서 내용 | search_esg_guideline |
| 품목·원자재·에너지 배출계수 조회 | search_emission_factor |
| 출장·운송 배출량 계산 | search_emission_factor |
| 구매 금액 기반 Scope3 배출량 | search_emission_factor |
| 실시간 ESG 뉴스·정보 | web_search_esg |
| 탄소 배출량 직접 계산 | calculate_carbon_emission |
| 용수 순환 분석 | analyze_water_resource_circulation |
| 안전 지표 계산 | calculate_safety |
| 직원 다양성 KPI 계산 | calculate_employee_kpi |
| ESG 법령·규제 최신 동향 검색 | search_esg_regulation |
| 윤리규범 자가 점검 및 리스크 진단 | score_ethics_risk |
| 동종업계 지배구조(G) 벤치마킹 | fetch_governance_benchmark |

## score_ethics_risk 툴 호출 규칙
1. 사용자가 윤리규범 현황을 언급하면, 언급된 정보만으로 즉시 툴을 호출합니다.
   - 언급되지 않은 항목은 responses에서 생략한다 (False로 자동 처리됨).
2. 모든 정보가 갖춰지지 않은 경우, 부분 정보로 먼저 결과를 출력합니다.
3. 툴 호출 후 응답 시 함수명 등 코드 관련 내용은 언급하지 않습니다.

## 답변 원칙
1. 질문에 특정 기업·연도·문서 유형이 언급되면 해당 필터를 사용해 검색하세요.
2. 검색 결과가 없으면 필터를 하나씩 제거하며 재검색하세요 (좁은 범위 → 넓은 범위).
3. [데이터 우선순위] 검색된 결과 중 정제한 마크다운(MD) 형식의 데이터가 있다면, 이를 최우선적으로 참조하여 수치의 정확성을 확보하세요.
4. `fetch_governance_benchmark` 호출 시, 결과는 반드시 (1)이사회 구성 (2)윤리강령 (3)위원회 현황으로 구분하여 3줄로 핵심만 요약하세요.
5. 탄소 배출량 계산 시 배출계수가 필요하면 search_emission_factor로 먼저 조회하세요.
6. 계산 과정을 단계별로 명확히 보여주세요.
7. 출처(기업명, 연도, 문서 유형)를 답변에 항상 포함하세요.
8. 가이드라인과 실제 기업 사례를 함께 제시하면 더욱 유용한 답변이 됩니다.
9. search_emission_factor 도구 사용 시, 사용자가 입력한 **'정확한 품목명 전체'**를 그대로 검색어(Query)로 사용하세요. 대충 요약하지 마세요.

## 특별 주의 사항 (강제 룰)
1. [다중 항목 계산] 여러 항목 계산 시 암산 금지. 각 항목별로 도구를 순차 호출한 뒤 합산하세요.
2. [Scope 분류] 출장, 숙박 등은 반드시 '간접 배출(Scope3)'로 명시하세요.
3. [결과물 포맷] 마크다운 형식을 사용하여 표, 볼드체, 리스트 등으로 작성하세요.
4. [실시간 환율 연동] epa_spend 계산 시 반드시 `web_search_esg`로 실시간 환율을 검색하여 반영하세요.
5. [답변 형식] 사용한 도구 이름, 내부 동작 과정은 절대 답변에 포함하지 마세요.
6. [ESG 가이드라인·보고서 질문] 해당 질문은 반드시 search_esg_guideline 툴을 호출하세요.
"""

    try:
        with open(BM25_CACHE_FILE, "rb") as f:
            docs = pickle.load(f)

        tree = defaultdict(lambda: defaultdict(set))
        all_categories = set()
        for doc in docs:
            meta = doc.metadata
            tree[meta.get('company', '알수없음')][meta.get('year', '?')].add(meta.get('doc_category', '문서'))
            all_categories.update(tree[meta.get('company', '알수없음')][meta.get('year', '?')])

        company_lines = [f"  - {c}: {', '.join(sorted(cats))} ({y})" 
                         for c, years in sorted(tree.items()) 
                         for y, cats in sorted(years.items())]

        doc_list = "[기업 보고서 목록]\n" + "\n".join(company_lines)
        category_list = "\n".join(f"  - '{c}'" for c in sorted(all_categories))

        return base_prompt.format(doc_list=doc_list, category_list=category_list)
    except:
        return base_prompt.format(doc_list=" (DB 미초기화)", category_list=" (N/A)")

# 에이전트 초기화
llm = ChatUpstage(model="solar-pro", temperature=0)

agent = create_react_agent(
    model=llm,
    tools=tools, 
    prompt=build_system_prompt(),
)

def run(messages: list) -> str:
    log_request(str(messages[-1].content) if messages else "")
    callback = LoggingCallbackHandler()
    start_time = time.time()
    try:
        result = agent.invoke(
            {"messages": messages},
            config={"recursion_limit": 10, "callbacks": [callback]},
        )
        response = result["messages"][-1].content
        log_response(response, time.time() - start_time, callback.tool_call_count)
        return response
    except Exception as e:
        return f"⚠️ 에이전트 실행 중 오류가 발생했습니다: {str(e)}"