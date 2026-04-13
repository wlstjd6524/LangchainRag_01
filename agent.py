import pickle
import os
from collections import defaultdict
from langchain_upstage import ChatUpstage
from langgraph.prebuilt import create_react_agent
from tools import tools

# Router 에 필요한 
from typing import Literal
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END, MessagesState

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

## 답변 원칙
1. 질문에 특정 기업·연도·문서 유형이 언급되면 해당 필터를 사용해 검색하세요.
2. 검색 결과가 없으면 필터를 하나씩 제거하며 재검색하세요 (좁은 범위 → 넓은 범위).
3. 탄소 배출량 계산 시 배출계수가 필요하면 search_emission_factor로 먼저 조회하세요.
4. 계산 과정을 단계별로 명확히 보여주세요.
5. 출처(기업명, 연도, 문서 유형)를 답변에 항상 포함하세요.
6. 가이드라인과 실제 기업 사례를 함께 제시하면 더욱 유용한 답변이 됩니다.
7. search_emission_factor 도구 사용 시, 사용자가 입력한 **'정확한 품목명 전체(예: 1종 포틀랜드 시멘트)'*를 그대로 검색어(Query)로 사용하세요. 대충 요약해서 검색하지 마세요.

## 특별 주의 사항 (강제 룰)
1. [다중 항목 계산] 질문에 계산해야 할 항목이 여러 개(예: 항공 출장 + 호텔 숙박)라면, 절대로 한 번에 암산하지 마세요. 반드시 각 항목별로 `search_emission_factor`와 `calculate_carbon_emission`을 개별적으로 순차 호출한 뒤, 마지막에 결과값을 합산하세요.
2. [Scope 분류] 출장, 숙박, 교통수단 이용 등은 반드시 '간접 배출(Scope3)'로 명시하세요.
3. [결과물 포맷] 마크다운 형식을 사용하여 표, 볼드체, 리스트 등으로 중소기업 담당자도 이해하기 쉽게 작성하세요.
4. [실시간 환율 연동] 구매 지출 기반(epa_spend) 배출량을 원화(KRW)로 계산할 경우, 반드시 `web_search_esg` 도구를 사용해 오늘의 실시간 USD/KRW 환율을 검색하세요. 검색된 환율로 원화 지출액을 USD로 변환한 뒤, DB의 '탄소배출계수(kg CO2e/USD)'를 적용하여 계산하세요. 
"""

    try:
        with open(BM25_CACHE_FILE, "rb") as f:
            docs = pickle.load(f)

        # 메타데이터 수집: {company: {year: set(doc_category)}}
        tree = defaultdict(lambda: defaultdict(set))
        for doc in docs:
            meta = doc.metadata
            company = meta.get('company', '알수없음')
            year = meta.get('year', '?')
            category = meta.get('doc_category', '문서')
            tree[company][year].add(category)

        # 공통 가이드라인과 기업 보고서 분리
        common_lines  = []
        company_lines = []
        all_categories = set()

        for company, years in sorted(tree.items()):
            for year, categories in sorted(years.items()):
                all_categories.update(categories)
                cats = ', '.join(sorted(categories))
                if company == '공통':
                    common_lines.append(f"  - ({year}) {cats}")
                else:
                    company_lines.append(f"  - {company}: {cats} ({year})")

        doc_list = ""
        if company_lines:
            doc_list += "[기업 보고서]\n" + "\n".join(company_lines)
        if common_lines:
            doc_list += "\n\n[공통 가이드라인] company='공통'으로 검색:\n" + "\n".join(common_lines)

        category_list = "\n".join(f"  - '{c}'" for c in sorted(all_categories))

        return base_prompt.format(
            doc_list=doc_list,
            category_list=category_list
        )

    except Exception:
        # BM25 캐시가 없을 경우 (ingest.py 미실행 상태) 기본 프롬프트 반환
        return base_prompt.format(
            doc_list="  (데이터베이스 미초기화 — ingest.py를 먼저 실행하세요)",
            category_list="  (데이터베이스 미초기화)"
        )


llm = ChatUpstage(model="solar-pro", temperature=0)

esg_agent = create_react_agent(
    model=llm,
    tools=tools,
    prompt=build_system_prompt(),
)

# Router Agent 영역

# ==========================================
# 1. 일상 대화(ChitChat) Node
# ==========================================
def chitchat_node(state: MessagesState):
    prompt = "당신은 ESG 공시 가이드 AI입니다. 사용자에게 친절하고 간결하게 인사하거나 대답해주세요. 도구(Tool)를 쓸 필요는 없습니다."
    response = llm.invoke([{"role": "system", "content": prompt}] + state["messages"])
    return {"messages": [response]}


# ==========================================
# 2. 라우터(의도를 분류하는 로직)
# ==========================================
class RouteQuery(BaseModel):
    destination: Literal["chitchat", "esg_task"] = Field(
        description="일상 대화면 'chitchat', 전문 작업(데이터 검색, 계산 등) 이면 'esg_task'를 선택하세요."
    )

router_prompt = ChatPromptTemplate.from_messages([
    ("system", """당신은 팀의 통합 AI 파이프라인 최상위 트래픽 라우터입니다.
사용자의 질문 의도를 분석하여 가장 적절한 경로로 연결하세요.

[분류 기준]
1. chitchat: "안녕", "고마워", "넌 누구야" 등 도구 호출이 전혀 필요 없는 단순 인사나 일상 대화.
2. esg_task: 기업 ESG 가이드라인 검색, 탄소/수자원 계산, 관련 뉴스 검색 등 팀원들이 구축한 데이터베이스나 도구(Tool)를 활용해야 하는 모든 전문적인 질문.
"""),
    ("user", "{question}")
])

router_chain = router_prompt | llm.with_structured_output(RouteQuery)


def route_question(state: MessagesState):
    '''
    사용자 질문을 분석해 다음 목적지로 반환
    '''
    question = state["messages"][-1].content
    print(f"[Router] 질문 의도 분석 : '{question}'")

    decision = router_chain.invoke({"question": question})
    print(f"분류 결과 : [{decision.destination}] 노드로 이동합니다.\n")

    return decision.destination


# ==========================================
# 3. 최상위 Supervisior 그래프 조립
# ==========================================
builder = StateGraph(MessagesState)

# 노드 추가 (기존에 만든 agent 를 esg_task 라는 이름으로 그대로 재투입)
builder.add_node("chitchat", chitchat_node)
builder.add_node("esg_task", esg_agent)

# 시작점에서 라우터(route_question) 로 분기 설정
builder.add_conditional_edges(START, route_question)

# 각 작업 끝나면 프로세스 종료
builder.add_edge("chitchat", END)
builder.add_edge("esg_task", END)

master_agent = builder.compile()


def run(messages: list) -> str:
    try:
        # 기존에 쓰던 agent.invoke -> master_agent.invoke 사용
        result = master_agent.invoke(
            {"messages": messages},
            # 라우터가 생겨서 limit 값 10 -> 15 로 변경
            config={"recursion_limit": 15},
        )
        return result["messages"][-1].content
    except Exception as e:
        return f"⚠️ 에이전트 실행 중 오류가 발생했습니다: {str(e)}"