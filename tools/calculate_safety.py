from langchain_core.tools import tool


@tool
def calculate_safety(
    total_hours_worked: float,
    lost_time_injuries: int,
    total_recordable_incidents: int,
) -> str:
    """
    사용자가 근로시간, 휴업재해 건수, 전체 재해 건수를 제시했을 때 호출한다.
    LTIR(휴업재해율)과 TRIR(전체재해율)을 계산한다.

    Args:
        total_hours_worked: 총 근로시간 (시간 단위)
        lost_time_injuries: 휴업재해 건수 (1일 이상 결근을 유발한 재해)
        total_recordable_incidents: 전체 기록 가능한 재해 건수 (휴업재해 포함)

    Returns:
        LTIR, TRIR 계산 결과 문자열
    """
    print("##### SAFETY TOOL #####")

    if total_hours_worked <= 0:
        return "오류: 총 근로시간은 0보다 커야 합니다."
    if lost_time_injuries < 0 or total_recordable_incidents < 0:
        return "오류: 재해 건수는 0 이상이어야 합니다."
    if lost_time_injuries > total_recordable_incidents:
        return "오류: 휴업재해 건수는 전체 재해 건수를 초과할 수 없습니다."

    # LTIR = (휴업재해 건수 × 200,000) / 총 근로시간
    # TRIR = (전체 재해 건수 × 200,000) / 총 근로시간
    # 200,000 = 100명 × 40시간/주 × 50주 (OSHA 기준 단위)
    BASE = 200_000

    ltir = (lost_time_injuries * BASE) / total_hours_worked
    trir = (total_recordable_incidents * BASE) / total_hours_worked

    return (
        f"[안전 지표 계산 결과]\n"
        f"  총 근로시간         : {total_hours_worked:,.0f} 시간\n"
        f"  휴업재해 건수       : {lost_time_injuries} 건\n"
        f"  전체 재해 건수      : {total_recordable_incidents} 건\n"
        f"\n"
        f"  LTIR (휴업재해율)   : {ltir:.4f}\n"
        f"  TRIR (전체재해율)   : {trir:.4f}\n"
        f"\n"
        f"  ※ 기준: 근로자 100명 × 연 2,000시간 (200,000 man-hours)"
    )
