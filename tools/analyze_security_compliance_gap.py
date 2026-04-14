import pandas as pd
from langchain_core.tools import tool

@tool
def analyze_security_compliance_gap(user_policy_desc: str, target_standard: str = "ISMS-P", keyword: str = "") -> str:
    """
    사용자의 현재 보안 정책이나 시스템 환경(user_policy_desc)을 입력 받아,
    ISMS-P 또는 ISO27001 인증 기준과 비교하여 누락된 점(Gap) 을 분석할 수 있도록
    관련된 보안 통제 항목 체크리스트를 반환.

    Args:
        user_policy_desc: 사용자가 입력한 현재 보안 상태 (ex: "방화벽 있고 비번 3개월 마다 바꿈)
        target_standard: "ISMS-P" (기본값) 또는 "ISO27001"
        keyword: 검색을 좁히기 위한 핵심 키워드 (ex: "비밀번호", "접근통제", "물리적")
    """

    # 1. 대상 DB 선택
    if target_standard.upper() == "ISO27001":
        file_path = "master_iso27001_checklist.csv"
    else:
        file_path = "master_isms_checklist.csv"

    try:
        df = pd.read_csv(file_path)
    except FileNotFoundError:
        return f"오류: {file_path} 데이터베이스 파일을 찾을 수 없습니다."
    

    # 2. 키워드 필터링 (사용자 상황과 관련된 조항만 추출해서 토큰 절약)
    if keyword:
        # 항목명, 상세내용, 주요확인사항 중에서 키워드가 포함된 행을 필터링
        mask = df.apply(lambda row: row.astype(str).str.contains(keyword, case=False, na=False).any(), axis=1)
        filtered_df = df[mask]
    else:
        # 키워드가 없으면 너무 많은 데이터를 반환 할 수 있어서 보호 로직 추가
        return "보안 영역이 너무 광범위합니다. 'keyword' 파라미터(ex: 접근통제, 개인정보)를 입력하여 다시 도구를 호출해주세요."
    
    if filtered_df.empty:
        return f"'{keyword}' 와(과) 관련된 {target_standard} 통제 항목을 찾을 수 없습니다. 다른 키워드로 검색해보세요."
    
    
    # 3. LLM이 분석하기 좋은 마크다운 텍스트 형태로 변환
    result_text = f"### {target_standard} [{keyword}] 관련 통제 항목\n"
    result_text += "에이전트는 아래의 기준표와 사용자의 상태('{user_policy_desc}')를 1:1로 비교하여, 충족된 부분과 누락된 부분(Gap)을 분석하여 답변하세요.\n\n"

    # 상위 10개 조항만 넘겨줘서 Context 길이 초과 방지
    for idx, row in filtered_df.head(10).iterrows():
        if target_standard == "ISMS-P":
            result_text += f"- **[{row['항목코드']}] {row['항목명']}**\n"
            result_text += f"  - 필수 확인사항: {row['주요 확인사항']}\n"
        else: # ISO 27001
            result_text += f"- **[{row['항목코드']}] {row['항목명']}**\n"
            result_text += f"  - 필수 확인사항: {row['상세내용']}\n"
    
    return result_text