import os
import boto3
from functools import lru_cache
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_upstage import ChatUpstage

load_dotenv()

S3_BUCKET    = os.getenv("S3_BUCKET",    "esg-agent-bucket")
S3_DB_PREFIX   = os.getenv("S3_DB_PREFIX",   "db/")
AWS_REGION   = os.getenv("AWS_REGION",   "ap-northeast-2")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "emission_factor.db")


def _download_db_from_s3():
    """로컬 DB 없을 때만 S3에서 다운로드"""
    if os.path.exists(DB_PATH):
        print("✅ 로컬 DB 캐시 사용 (S3 다운로드 스킵)")
        return

    print("☁️  로컬 DB 없음 → S3에서 다운로드 중...")
    s3 = boto3.client(
        "s3",
        region_name=AWS_REGION,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )
    s3_key = f"{S3_DB_PREFIX}emission_factor.db"
    try:
        s3.download_file(S3_BUCKET, s3_key, DB_PATH)
        print("✅ DB 다운로드 완료")
    except Exception as e:
        print(f"⚠️  DB 다운로드 실패: {e}\ningest_csv.py를 먼저 실행해주세요.")
        raise


_download_db_from_s3()


@lru_cache(maxsize=1)
def _get_sql_agent():
    db  = SQLDatabase.from_uri(f"sqlite:///{DB_PATH}")
    llm = ChatUpstage(model="solar-pro", temperature=0)

    return create_sql_agent(
        llm=llm,
        db=db,
        agent_type="openai-tools",
        verbose=os.getenv("DEBUG", "false").lower() == "true",
        prefix="""
당신은 탄소 배출계수 데이터베이스 전문 SQL 분석가입니다.

## 테이블 구조

### 1. korea_lci — 국내 LCI 탄소배출계수
| 컬럼 | 설명 | 예시 |
|------|------|------|
| 대분류 | 품목 대분류 | '원료 및 에너지 생산', '수송' |
| 구분 | 중분류 | '건축자재', '화학제품' |
| 품목명 | 세부 품목명 | '1종 포틀랜드 시멘트' |
| 단위 | 기준 단위 | 'kg', 'MJ', 'km' |
| 탄소배출계수 | kg CO2eq / 단위 | 0.926326 |

### 2. defra_scope3 — DEFRA Scope3 배출계수 (해외 출장/운송)
| 컬럼 | 설명 | 예시 |
|------|------|------|
| 카테고리(한글) | 활동 유형 한글명 | '항공 출장', '육상 출장' |
| 영문_대분류 | 영문 대분류 | 'Flights', 'Cars (by market segment)' |
| 영문_소분류 | 영문 세부 분류 | 'Domestic, to/from UK', 'Mini' |
| 단위 | 기준 단위 | 'passenger.km', 'km' |
| 탄소배출계수 | kg CO2eq / 단위 | 0.272577 |

### 3. epa_spend — EPA 지출 기반 배출계수 (Scope3 구매)
| 컬럼 | 설명 | 예시 |
|------|------|------|
| 카테고리(한글) | 산업/품목 한글명 | '대두 농업', '철강 제조' |
| 영문_산업분류명 | 영문 산업분류 | 'Soybean Farming' |
| 탄소배출계수(kg CO2e/1만원) | 1만원 지출 기준 | 11.5909 |
| 탄소배출계수(kg CO2e/USD) | 1달러 지출 기준 | 1.326 |

## 쿼리 작성 지침
1. 품목/활동 검색 시 LIKE '%키워드%' 로 유연하게 검색
2. 탄소 배출량 계산 시: 활동량 × 탄소배출계수
3. epa_spend는 구매 금액 기반, 나머지는 활동량(무게/거리) 기반
4. 컬럼명에 괄호가 있으므로 반드시 큰따옴표로 감쌀 것 (예: "탄소배출계수(kg CO2e/1만원)")
        """,
    )


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
        result = _get_sql_agent().invoke({"input": query})
        return result["output"]
    except Exception as e:
        print(f"[search_emission_factor ERROR] {e}")
        raise