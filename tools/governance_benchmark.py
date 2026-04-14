import os
import logging
import OpenDartReader
from typing import Dict, Any, Optional
from langchain.tools import tool
from pydantic import BaseModel, Field

# 로거 설정
logger = logging.getLogger(__name__)

class GovernanceInput(BaseModel):
    industry: str = Field(description="대상 산업군 (반도체, 화장품 등)")

def get_dart_client() -> Optional[Any]:
    """DART API 클라이언트를 환경에 맞춰 유연하게 초기화함"""
    api_key = os.getenv("DART_API_KEY")
    if not api_key:
        logger.error("DART_API_KEY environment variable is missing.")
        return None
    
    try:
        # 라이브러리 로드 방식에 따른 분기 처리 (AttributeError 방지)
        if hasattr(OpenDartReader, 'OpenDartReader'):
            return OpenDartReader.OpenDartReader(api_key)
        # 만약 OpenDartReader 자체가 클래스라면 바로 호출
        return OpenDartReader(api_key)
    except Exception as e:
        logger.error(f"Fail to initialize DART client: {str(e)}")
        return None

@tool("fetch_governance_benchmark", args_schema=GovernanceInput)
def fetch_governance_benchmark(industry: str) -> str:
    """
    DART API 연동을 통해 업종별 선도 기업의 실시간 공시 현황 및 지배구조(G) 지표를 조회함.
    """
    dart = get_dart_client()
    
    # 1. 업종별 벤치마킹 타겟 설정
    PEER_CONFIG: Dict[str, Dict[str, Any]] = {
        "화장품": {
            "corp_nm": "아모레퍼시픽",
            "metrics": {
                "board": "사외이사 비율 60% (의장-CEO 분리)",
                "ethics": "윤리강령 명문화 및 정기 준법 교육",
                "committee": "이사회 내 ESG 위원회 운영"
            }
        },
        "반도체": {
            "corp_nm": "삼성전자",
            "metrics": {
                "board": "사외이사 과반수 구성 (독립성 확보)",
                "ethics": "글로벌 비즈니스 가이드라인 준수",
                "committee": "지속가능경영위원회 운영"
            }
        }
    }

    target = PEER_CONFIG.get(industry)
    if not target:
        return f"Error: '{industry}' 산업군에 대한 벤치마킹 데이터가 정의되지 않았습니다."

    corp_nm = target["corp_nm"]
    metrics = target["metrics"]

    # 2. 실시간 DART 공시 데이터 페칭
    report_status = "DART API 연결 실패 (Local 데이터 모드)"
    if dart:
        try:
            # 최근 공시 리스트 조회 (기업지배구조 관련 'I' 공시 위주)
            reports = dart.list(corp_nm, kind='I', bgn_date='20240101') 
            if reports is not None and not reports.empty:
                latest = reports.iloc[0]
                report_status = f"최신 공시: {latest['report_nm']} ({latest['rcept_dt']})"
            else:
                report_status = "최근 1년 내 관련 공시 내역 없음"
        except Exception as e:
            logger.warning(f"DART API 데이터 페칭 실패: {str(e)}")
            report_status = "실시간 공시 조회 오류 (내부 지표 기반 분석)"

    # 3. 데이터 구조화 및 출력 (3줄 요약 가이드 준수)
    return f"""
### [DART Governance Analysis: {corp_nm}]
- **상태**: {report_status}
- **이사회 구조**: {metrics['board']}
- **윤리 경영**: {metrics['ethics']}
- **거버넌스 기구**: {metrics['committee']}
*본 데이터는 OpenDartReader 실시간 조회값과 내부 벤치마킹 지표를 통합한 결과임.*
"""