import os
import re
import boto3
from functools import lru_cache
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.utilities import SQLDatabase
from langchain_upstage import ChatUpstage
from langgraph.graph import END, START, MessagesState, StateGraph

load_dotenv()

S3_BUCKET    = os.getenv("S3_BUCKET",    "esg-agent-bucket")
S3_DB_PREFIX = os.getenv("S3_DB_PREFIX", "db/")
AWS_REGION   = os.getenv("AWS_REGION",   "ap-northeast-2")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "emission_factor.db")


def _download_db_from_s3():
    if os.path.exists(DB_PATH):
        print("로컬 DB 캐시 사용 (S3 다운로드 스킵)")
        return
    print("☁️ 로컬 DB 없음 → S3에서 다운로드 중...")
    s3 = boto3.client(
        "s3",
        region_name=AWS_REGION,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )
    s3_key = f"{S3_DB_PREFIX}emission_factor.db"
    try:
        s3.download_file(S3_BUCKET, s3_key, DB_PATH)
        print("DB 다운로드 완료")
    except Exception as e:
        print(f"⚠️ DB 다운로드 실패: {e}\ningest_csv.py를 먼저 실행해주세요.")
        raise


_download_db_from_s3()

GENERATE_QUERY_SYSTEM = """You are a SQLite SQL expert for a Korean carbon emission factor database.
Output the SQL query strictly inside a ```sql ... ``` code block. No explanation.
NO DML statements (INSERT, UPDATE, DELETE, DROP).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【TABLE 1】 korea_lci  — 국내 LCI 배출계수
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Columns: 대분류, 구분, 품목명, 단위, 탄소배출계수

** 분류별 컬럼 역할이 다름 (반드시 구분할 것):

[일반 대분류] 원료 및 에너지 생산 / 수송 / 폐기물 처리 / 화학반응공정
  구분   = 카테고리 (예: '에너지', '건축자재', '소각', '매립', '육상수송')
  품목명 = 실제 품목 (예: '경유', '전기', '폐지 소각', '유기성폐기물 소각', '트럭')
  → 품목 검색: WHERE REPLACE(품목명,' ','') LIKE '%검색어%'

[특수 대분류] 연료원별 사용  ← 구분/품목명 역할이 반전됨
  구분   = 연료 종류 (실제 저장된 이름 목록):
    'LNG(천연가스)', 'LPG(액화석유가스)', '경유', '등유', '휘발유', '나프타',
    'B-A유', 'B-B유', 'B-C유', '항공유', '아스팔트', '윤활유', '코크스',
    '석유코크스', '국내무연탄', '수입무연탄_연료용', '수입무연탄_원료용',
    '연료용 유연탄(역청탄)', '원료용 유연탄(역청탄)'
  품목명 = 사용 부문/용도 (예: '제조업 및 건설', '육상 수송', '가정', '에너지산업')
  → 연료 검색: WHERE 대분류='연료원별 사용' AND REPLACE(구분,' ','') LIKE '%연료명%'


** UNION ALL 필수 연료 목록 (아래 연료는 반드시 UNION ALL 사용)

아래 연료들은 두 대분류에 모두 데이터가 존재하며, 단위와 의미가 다름.
원료 및 에너지 생산(품목명, kg기준) ↔ 연료원별 사용(구분, L 또는 m³기준)

  경유      ↔  경유            (원료생산LCI kg/kg  vs  연소 L/L)
  등유      ↔  등유            (원료생산LCI kg/kg  vs  연소 L/L)
  휘발유    ↔  휘발유          (원료생산LCI kg/kg  vs  연소 L/L)
  나프타    ↔  나프타          (원료생산LCI kg/kg  vs  연소 L/L)
  천연가스  ↔  LNG(천연가스)   (원료생산LCI kg/kg  vs  연소 m³/m³) ← 이름 다름 주의
  액화석유가스(LPG) ↔ LPG(액화석유가스) (원료생산LCI kg/kg vs 연소 kg/kg) ← 이름 다름 주의

위 연료 검색 템플릿 (반드시 이 형식 사용):
  SELECT 대분류, 구분, 품목명, 단위, 탄소배출계수 FROM korea_lci
  WHERE 대분류 != '연료원별 사용' AND REPLACE(품목명,' ','') LIKE '%키워드%'
  UNION ALL
  SELECT 대분류, 구분, 품목명, 단위, 탄소배출계수 FROM korea_lci
  WHERE 대분류 = '연료원별 사용' AND REPLACE(구분,' ','') LIKE '%키워드%'

괄호 포함 이름 검색 규칙 (OR로 키워드 분리):
  DB에 'LNG(천연가스)', 'LPG(액화석유가스)' 처럼 괄호가 포함된 이름이 있음.
  사용자가 'LNG' 또는 '천연가스' 어느 쪽으로 물어봐도 찾을 수 있도록
  괄호 앞 이름과 괄호 안 이름을 OR 로 분리하여 검색:
    REPLACE(구분,' ','') LIKE '%LNG%' OR REPLACE(구분,' ','') LIKE '%천연가스%'
    REPLACE(구분,' ','') LIKE '%LPG%' OR REPLACE(구분,' ','') LIKE '%액화석유가스%'

실용 예시:
  Q: "LNG 배출계수" 또는 "천연가스 배출계수"  → 같은 SQL로 처리
     SELECT 대분류, 구분, 품목명, 단위, 탄소배출계수 FROM korea_lci
     WHERE 대분류 != '연료원별 사용'
       AND (REPLACE(품목명,' ','') LIKE '%LNG%' OR REPLACE(품목명,' ','') LIKE '%천연가스%')
     UNION ALL
     SELECT 대분류, 구분, 품목명, 단위, 탄소배출계수 FROM korea_lci
     WHERE 대분류 = '연료원별 사용'
       AND (REPLACE(구분,' ','') LIKE '%LNG%' OR REPLACE(구분,' ','') LIKE '%천연가스%')

  Q: "경유 배출계수"
     SELECT 대분류, 구분, 품목명, 단위, 탄소배출계수 FROM korea_lci
     WHERE 대분류 != '연료원별 사용' AND REPLACE(품목명,' ','') LIKE '%경유%'
     UNION ALL
     SELECT 대분류, 구분, 품목명, 단위, 탄소배출계수 FROM korea_lci
     WHERE 대분류 = '연료원별 사용' AND REPLACE(구분,' ','') LIKE '%경유%'

  Q: "폐지 소각 배출계수"  → 폐기물처리는 일반 대분류, UNION ALL 불필요
     SELECT 구분, 품목명, 단위, 탄소배출계수 FROM korea_lci
     WHERE REPLACE(품목명,' ','') LIKE '%폐지소각%'

  Q: "트럭 운송 배출계수"  → 수송은 일반 대분류, UNION ALL 불필요
     SELECT 구분, 품목명, 단위, 탄소배출계수 FROM korea_lci
     WHERE 대분류='수송' AND REPLACE(품목명,' ','') LIKE '%트럭%'

대분류 전체 목록: '원료 및 에너지 생산', '수송', '폐기물 처리', '연료원별 사용', '화학반응공정'

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【TABLE 2】 defra_scope3  — 해외 출장/운송 배출계수
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Columns: 카테고리(한글), 영문_대분류, 영문_소분류, 단위, 탄소배출계수

카테고리(한글) 목록: '항공 출장', '육상 출장', '해운 출장', '화물 운송',
                     '상수도(물 공급)', '하수 처리', '원자재 구매', '호텔 숙박',
                     '전력 송배전 손실', '전기차 전력 송배전 손실', '재택근무'

검색: WHERE REPLACE("카테고리(한글)",' ','') LIKE '%키워드%'
      OR REPLACE(영문_대분류,' ','') LIKE '%keyword%'

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【TABLE 3】 epa_spend  — 지출 기반 배출계수 (Scope3)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Columns: 카테고리(한글), 영문_산업분류명,
         "탄소배출계수(kg CO2e/1만원)", "탄소배출계수(kg CO2e/USD)"

카테고리(한글) 컬럼의 99%가 영문 그대로 저장됨.
   반드시 한글 + 영문 동시 검색:
   WHERE REPLACE("카테고리(한글)",' ','') LIKE '%한글키워드%'
      OR REPLACE(영문_산업분류명,' ','') LIKE '%EnglishKeyword%'

컬럼명에 괄호 포함 시 큰따옴표 필수:
   ✅ "탄소배출계수(kg CO2e/1만원)"   ❌ 탄소배출계수(kg CO2e/1만원)

【공통 규칙】
한국어 텍스트는 DB 내 띄어쓰기가 불일치함.
모든 한국어 검색 시 REPLACE(컬럼,' ','') LIKE '%공백없는키워드%' 패턴 사용.

🚨 [절대 준수: 토큰 폭주 및 무한 루프 방지 제약사항] 🚨
1. 마크다운 필수: 쿼리가 끝났음을 시스템이 인지할 수 있도록, 반드시 ```sql 과 ``` 블록으로 쿼리를 감싸서 출력하세요.
2. 다중 키워드 동시 검색 (매우 중요): 사용자가 '항공 출장'과 '호텔 숙박'처럼 여러 개를 동시에 물어볼 경우, 절대 SELECT 문을 여러 개 만들지 마세요. 단 1개의 SELECT 문 안에서 `WHERE (카테고리 LIKE '%항공%' OR 카테고리 LIKE '%호텔%')` 처럼 OR 조건으로 묶어서 한 번에 조회하세요.
3. 단일 테이블 원칙: defra_scope3, epa_spend, korea_lci 중 단 1개의 테이블만 선택하세요. 테이블 간 UNION ALL은 절대 금지합니다.
4. UNION ALL 예외: 오직 'korea_lci' 테이블 내부에서 일반 대분류와 '연료원별 사용'을 합칠 때만 예외적으로 UNION ALL을 허용합니다.
5. LIMIT 5 문법: 결과 폭주를 막기 위해 전체 쿼리의 맨 마지막에 반드시 `LIMIT 5`를 딱 한 번만 붙이세요.
"""

GENERATE_QUERY_USER = """Schema (for reference):
{schema}

User Question: {question}

Previous attempts and errors (if any):
{history}

SQL Query (raw SQL only, no backticks):"""

ANSWER_SYSTEM = """당신은 탄소 배출계수 데이터베이스 분석 전문가입니다.
사용자 질문, 실행된 SQL, DB 조회 결과를 바탕으로 한국어로 답변하세요.

절대 규칙:
1. DB 조회 결과의 숫자를 그대로 사용하세요. 절대 다른 값으로 바꾸지 마세요.
2. 결과가 비어 있으면 "데이터베이스에서 해당 항목을 찾을 수 없습니다"라고만 답하세요.
3. DB 결과에 없는 수치를 추가로 언급하지 마세요.
4. 연료원별 사용 결과는 사용 부문(용도)별로 표로 정리하세요.
"""

ANSWER_USER = """질문: {question}
실행된 SQL: {sql}
DB 조회 결과: {result}"""


def _sanitize_sql(text: str) -> str:
    m = re.search(r"```(?:sql)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    return (m.group(1) if m else text).strip()


@lru_cache(maxsize=1)
def _get_db_and_llm():
    db  = SQLDatabase.from_uri(f"sqlite:///{DB_PATH}")
    llm = ChatUpstage(model="solar-pro", temperature=0)
    return db, llm


def _build_sql_pipeline():
    db, llm = _get_db_and_llm()
    schema_info = db.get_table_info()

    generate_prompt = ChatPromptTemplate.from_messages([
        ("system", GENERATE_QUERY_SYSTEM),
        ("user",   GENERATE_QUERY_USER),
    ])
    answer_prompt = ChatPromptTemplate.from_messages([
        ("system", ANSWER_SYSTEM),
        ("user",   ANSWER_USER),
    ])

    def generate_query(state: MessagesState):
        print("##### GENERATE QUERY #####")
        question = state["messages"][0].content
        history  = "\n".join(
            m.content for m in state["messages"][1:]
            if hasattr(m, "content") and m.content
        )
        response = llm.invoke(generate_prompt.format_messages(
            schema=schema_info,
            question=question,
            history=history or "없음",
        ))
        print(f"생성된 SQL:\n{response.content}")
        return {"messages": [response]}

    def execute_query(state: MessagesState):
        print("##### EXECUTE QUERY #####")
        raw_sql = state["messages"][-1].content
        sql     = _sanitize_sql(raw_sql)
        result  = db.run_no_throw(sql)
        print(f"실행 결과: {result}")
        if not result:
            result = "Error: 쿼리 실행 실패 또는 결과 없음. 다른 키워드나 컬럼으로 재시도하세요."
        return {"messages": [AIMessage(content=str(result))]}

    def answer(state: MessagesState):
        print("##### ANSWER #####")
        question = state["messages"][0].content
        sql      = state["messages"][-2].content
        result   = state["messages"][-1].content
        response = llm.invoke(answer_prompt.format_messages(
            question=question, sql=sql, result=result,
        ))
        return {"messages": [response]}

    def should_retry(state: MessagesState):
        last_content = state["messages"][-1].content
        error_count  = sum(
            1 for m in state["messages"]
            if hasattr(m, "content") and "Error:" in (m.content or "")
        )
        if ("Error:" in last_content or "error" in last_content.lower()) and error_count < 2:
            print(f"오류 감지 → 쿼리 재생성 (시도 {error_count + 1}/2)")
            return "generate_query"
        return "answer"

    graph = StateGraph(MessagesState)
    graph.add_node("generate_query", generate_query)
    graph.add_node("execute_query",  execute_query)
    graph.add_node("answer",         answer)
    graph.add_edge(START,            "generate_query")
    graph.add_edge("generate_query", "execute_query")
    graph.add_conditional_edges(
        "execute_query", should_retry,
        {"generate_query": "generate_query", "answer": "answer"},
    )
    graph.add_edge("answer", END)
    return graph.compile()


@lru_cache(maxsize=1)
def _get_sql_pipeline():
    return _build_sql_pipeline()


@tool
def search_emission_factor(query: str) -> str:
    """
    탄소 배출계수 데이터베이스를 조회하는 도구입니다.
    아래 3가지 유형의 질문에 사용하세요:

    1. 활동 기반 배출계수 (korea_lci):
       - 특정 품목/원자재의 탄소배출계수 조회
       - 예: "시멘트 탄소배출계수", "전기 배출계수", "경유 배출계수"

    2. 출장/운송 배출계수 (defra_scope3):
       - 항공·육상·해상 출장/운송의 배출계수 조회
       - 예: "국내선 항공 배출계수", "승용차 km당 배출량"

    3. 구매 지출 기반 배출계수 (epa_spend):
       - 구매 금액 기준 탄소 배출량 계산
       - 예: "철강 구매 배출계수", "1만원당 IT장비 탄소 배출량"
    """
    try:
        pipeline = _get_sql_pipeline()
        result   = pipeline.invoke({"messages": [{"role": "user", "content": query}]})
        return result["messages"][-1].content
    except Exception as e:
        print(f"[search_emission_factor ERROR] {e}")
        raise