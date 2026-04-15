import pickle
import os
import time
from collections import defaultdict
from typing import Literal
from langchain_upstage import ChatUpstage
from langgraph.prebuilt import create_react_agent
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END, MessagesState
from tools import tools
from middleware.logger import LoggingCallbackHandler, log_request, log_response
from middleware.summarizer import should_summarize, summarize_messages

VECTORSTORE_DIR = "./vectorstore"
BM25_CACHE_FILE = os.path.join(VECTORSTORE_DIR, "bm25_docs.pkl")

def build_system_prompt() -> str:
    """
    BM25 캐시에서 메타데이터를 읽어 보유 문서 목록을 자동 생성합니다.
    파일이 추가/삭제되어도 ingest.py 재실행 후 자동으로 반영됩니다.
    """
    base_prompt = """당신은 ESG 공시 전문 가이드 에이전트입니다.
기업의 ESG(환경·사회·지배구조) 공시 관련 질문에 답변하고, 보고서 작성을 지원합니다.

## ⚠️ 최우선 규칙: 숫자 날조 절대 금지
모든 수치는 반드시 도구를 호출하여 데이터베이스에서 가져와야 하며, 추측 답변을 엄격히 금지합니다.

**search_emission_factor 툴 호출 필수 조건 (아래 중 하나라도 해당하면 무조건 호출)**
1. "배출계수", "탄소배출계수", "발생계수" 단어가 포함된 질문
2. 특정 연료·에너지·원자재·화학물질·폐기물 사용량이 언급되고 탄소/배출/계산이 요청된 질문
   예시: "LNG 5,000m3 사용했어, 탄소 배출량은?", "경유 100L 사용 시 배출량", "전기 15,000kWh 사용"
3. 에너지원 이름(LNG, LPG, 경유, 휘발유, 도시가스, 등유, 전기, 석탄 등)이 언급된 질문
4. 원자재·건축자재·화학물질 이름이 언급된 질문
5. 폐기물 처리(매립, 소각, 재활용) 관련 질문
6. 출장·운송(항공, 차량, 선박) 탄소 관련 질문
7. 구매 금액 기반 Scope3 배출량 질문

**처리 규칙 (절대 위반 금지)**
1. 위 조건 중 하나라도 해당하면 search_emission_factor를 먼저 호출하세요.
2. 툴을 호출하지 않고 배출계수 숫자를 직접 답변하는 것은 엄격히 금지입니다.
3. 툴 결과에 있는 숫자를 그대로 사용하세요. 수정하거나 추가 계수를 덧붙이지 마세요.
4. 툴이 "찾을 수 없다"고 반환하면, 추측값 없이 그대로 사용자에게 전달하세요.

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
| ESG 정책, 가이드라인, 보고서 내용, 침해사고 대응 매뉴얼, 보안 인증제도 절차 및 수수료 검색 | search_esg_guideline |
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
| 기업 보안 정책 진단 및 인증 기준(ISMS-P, ISO27001) 누락 항목 분석 | analyze_security_compliance_gap |
| 동종업계 지배구조(G) 벤치마킹 | fetch_governance_benchmark |

## score_ethics_risk 툴 호출 규칙
1. 사용자가 윤리규범 현황을 언급하면, 언급된 정보만으로 즉시 툴을 호출합니다.
   - 언급되지 않은 항목은 responses에서 생략한다 (False로 자동 처리됨).
2. 모든 정보가 갖춰지지 않은 경우, 부분 정보로 먼저 결과를 출력합니다.
3. 툴 호출 후 응답 시 함수명 등 코드 관련 내용은 언급하지 않습니다.

## 답변 원칙
1. 질문에 특정 기업·연도·문서 유형이 언급되면 해당 필터를 사용해 검색하세요.
2. 검색 결과가 없으면 필터를 하나씩 제거하며 재검색하세요 (좁은 범위 → 넓은 범위).
3. 탄소 배출량 계산 시 배출계수가 필요하면 search_emission_factor로 먼저 조회하세요.
4. 계산 과정을 단계별로 명확히 보여주세요.
5. 출처(기업명, 연도, 문서 유형)를 답변에 항상 포함하세요.
6. 가이드라인과 실제 기업 사례를 함께 제시하면 더욱 유용한 답변이 됩니다.
7. search_emission_factor 도구 사용 시, 사용자가 입력한 **'정확한 품목명 전체(예: 1종 포틀랜드 시멘트)'**를 그대로 검색어(Query)로 사용하세요. 대충 요약해서 검색하지 마세요.
8. 검색된 결과 중 정제한 마크다운(MD) 형식의 데이터가 있다면, 이를 최우선적으로 참조하여 수치의 정확성을 확보하세요.
9.[G-Benchmarking 출력 규칙]
       - 단순 현황 조회 시: (1)이사회 구성 (2)윤리강령 (3)위원회 현황으로 구분하여 3줄로 핵심만 요약하세요.
       - 비교 분석/벤치마킹 요청 시: 마크다운 표(Table)를 활용하여 업종 평균 및 선도 기업과 대조하여 상세히 답변하세요.

## 특별 주의 사항 (강제 룰)
1. [다중 항목 계산] 질문에 계산해야 할 항목이 여러 개(예: 항공 출장 + 호텔 숙박)라면, 절대로 한 번에 암산하지 마세요. 반드시 각 항목별로 `search_emission_factor`와 `calculate_carbon_emission`을 개별적으로 순차 호출한 뒤, 마지막에 결과값을 합산하세요.
2. [Scope 분류] 출장, 숙박, 교통수단 이용 등은 반드시 '간접 배출(Scope3)'로 명시하세요.
3. [결과물 포맷] 마크다운 형식을 사용하여 표, 볼드체, 리스트 등으로 중소기업 담당자도 이해하기 쉽게 작성하세요.
4. [실시간 환율 연동] 구매 지출 기반(epa_spend) 배출량을 원화(KRW)로 계산할 경우, 반드시 `web_search_esg` 도구를 사용해 오늘의 실시간 USD/KRW 환율을 검색하세요. 검색된 환율로 원화 지출액을 USD로 변환한 뒤, DB의 '탄소배출계수(kg CO2e/USD)'를 적용하여 계산하세요.
5. [답변 형식] 사용한 도구 이름, 재검색 안내, 내부 동작 과정은 절대 답변에 포함하지 마세요. 사용자는 도구의 존재를 알 필요가 없습니다.
6. [ESG 가이드라인·보고서 질문] ESG 가이드라인, 기업 보고서, 공시 항목 관련 질문은 반드시 search_esg_guideline 툴을 호출하세요. 적합한 문서가 없을 데이터베이스에 없을 경우 자체 지식 말고 검색해서 답변할지 사용자에게 제안하세요.
"""

    try:
        if not os.path.exists(BM25_CACHE_FILE):
             raise FileNotFoundError("BM25 캐시 파일이 없습니다.")

        with open(BM25_CACHE_FILE, "rb") as f:
            docs = pickle.load(f)

        tree = defaultdict(lambda: defaultdict(set))
        all_categories = set()
        for doc in docs:
            meta = doc.metadata
            tree[meta.get('company', '알수없음')][meta.get('year', '?')].add(meta.get('doc_category', '문서'))
            all_categories.add(meta.get('doc_category', '문서'))

        company_lines = [f"  - {c}: {', '.join(sorted(cats))} ({y})" 
                         for c, years in sorted(tree.items()) 
                         for y, cats in sorted(years.items())]

        doc_list = "[기업 보고서 목록]\n" + "\n".join(company_lines)
        category_list = "\n".join(f"  - '{c}'" for c in sorted(all_categories))

        return base_prompt.format(doc_list=doc_list, category_list=category_list)
    except Exception:
        return base_prompt.format(
            doc_list="  (데이터베이스 미초기화 — ingest.py를 먼저 실행하세요)",
            category_list="  (데이터베이스 미초기화)"
        )

# 1. ESG 태스크 에이전트 (React Agent)
llm = ChatUpstage(model="solar-pro", temperature=0)
esg_agent = create_react_agent(
    model=llm,
    tools=tools, 
    prompt=build_system_prompt(),
)

# 2. 일상 대화 노드 (Chitchat)
def chitchat_node(state: MessagesState):
    prompt = "당신은 ESG 공시 가이드 AI입니다. 사용자에게 친절하고 간결하게 인사하거나 대답해주세요. 도구(Tool)를 쓸 필요는 없습니다."
    response = llm.invoke([{"role": "system", "content": prompt}] + state["messages"])
    return {"messages": [response]}

# 3. 라우터 로직 (Router)
class RouteQuery(BaseModel):
    destination: Literal["chitchat", "esg_task"] = Field(
        description="일상 대화면 'chitchat', 전문 작업(데이터 검색, 계산 등) 이면 'esg_task'를 선택하세요."
    )

router_prompt = ChatPromptTemplate.from_messages([
    ("system", """당신은 팀의 통합 AI 파이프라인 최상위 트래픽 라우터입니다.
사용자의 질문 의도를 분석하여 가장 적절한 경로로 연결하세요."""),
    ("user", "{question}")
])
router_chain = router_prompt | llm.with_structured_output(RouteQuery)

def route_question(state: MessagesState):
    question = state["messages"][-1].content
    decision = router_chain.invoke({"question": question})
    return decision.destination

# 4. 전체 마스터 그래프 구축
builder = StateGraph(MessagesState)
builder.add_node("chitchat", chitchat_node)
builder.add_node("esg_task", esg_agent)
builder.add_conditional_edges(START, route_question)
builder.add_edge("chitchat", END)
builder.add_edge("esg_task", END)

master_agent = builder.compile()

def run(messages: list) -> tuple[str, list]:
    """
    최종 엔트리 포인트.
    Returns:
        (response, updated_messages): 응답 문자열과 요약이 반영된 메시지 리스트
    """
    from langchain_core.messages import AIMessage

    if should_summarize(messages):
        messages = summarize_messages(messages, llm)

    log_request(str(messages[-1].content) if messages else "")
    callback = LoggingCallbackHandler()
    start_time = time.time()

    try:
        result = master_agent.invoke(
            {"messages": messages},
            config={
                "recursion_limit": 15,
                "callbacks": [callback]
            },
        )
        response = result["messages"][-1].content
        log_response(response, time.time() - start_time, callback.tool_call_count)
        updated_messages = messages + [AIMessage(content=response)]
        return response, updated_messages
    except Exception as e:
        error_msg = f"⚠️ 에이전트 실행 중 오류가 발생했습니다: {str(e)}"
        return error_msg, messages