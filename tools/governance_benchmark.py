import os
import logging
from typing import Dict, Any
from langchain.tools import tool
from pydantic import BaseModel, Field

# 운영 로그 설정
logger = logging.getLogger(__name__)

class GovernanceInput(BaseModel):
    industry: str = Field(description="대상 산업군 (반도체, 화장품 등)")

@tool("fetch_governance_benchmark", args_schema=GovernanceInput)
def fetch_governance_benchmark(industry: str) -> str:
    """
    DART 공시 기반 업종별 선도 기업의 지배구조(G) 핵심 지표를 조회함.
    """
    # 1. 산업별 리딩 기업 데이터셋 (Mock Data)
    PEER_METRICS: Dict[str, Dict[str, Any]] = {
        "화장품": {
            "corp_nm": "아모레퍼시픽",
            "board": "사외이사 비율 60% (의장-CEO 분리 선임)",
            "ethics": "전사적 윤리강령 준수 및 정기 컴플라이언스 교육",
            "committee": "ESG 위원회 및 내부회계관리제도 활성화",
            "ref": "2024 지배구조보고서"
        },
        "반도체": {
            "corp_nm": "삼성전자",
            "board": "사외이사 과반수 구성 (독립성 보장)",
            "ethics": "글로벌 비즈니스 가이드라인 및 제보자 보호 시스템",
            "committee": "지속가능경영위원회(사외이사 전원)",
            "ref": "2024 지속가능경영보고서"
        }
    }

    # API Key 미설정 시 경고 처리
    if not os.getenv("DART_API_KEY"):
        logger.warning("DART_API_KEY is missing. Using local metrics.")

    # 2. 데이터 추출 및 반환
    target = PEER_METRICS.get(industry)
    if not target:
        return f"Warning: '{industry}' 산업군 데이터가 매핑되지 않았습니다."

    return f"""
[DART Benchmarking: {target['corp_nm']}]
- Reference: {target['ref']}
- 이사회 구조: {target['board']}
- 윤리경영: {target['ethics']}
- 위원회 현황: {target['committee']}
*API 승인 대기 중으로 로컬 데이터를 반환함.*
"""