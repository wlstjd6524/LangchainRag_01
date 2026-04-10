from langchain_core.tools import tool

@tool
def calculate_carbon_emission(activity_amount: float, emission_factor: float, multiplier: float = 1.0, unit: str = "") -> str:
    """
    활동량(또는 지출액) 과 DB 에서 검색된 탄소 배출계수를 곱하여 최종 탄소 배출량을 안전하게 계산합니다.
    필요한 경우 인원수, 숙박 일수, 횟수 등의 추가 곱셈 값(multiplier) 을 넣을 수 있습니다.
    반드시 search_emission_factor 도구로 배출계수를 먼저 찾은 다음에, 이 도구에 숫자를 넣어 호출해야 합니다.

    Args:
        activity_amount: 사용자의 활동량 또는 지출액 숫자 (ex: 500)
        emission_factor: DB에서 조회해 온 탄소 배출계수 숫자 (ex: 0.6695)
        multiplier: 인원수, 대수 등 추가로 곱해야 하는 배수 (기본값 1.0, 예: 3명 출장이면 3.0 입력)
        unit: 결과에 표시할 단위 (ex: "만원", "kg", "km")
    """
    print(f"##### [TOOL] CALCULATING EMISSION: {activity_amount} * {emission_factor} * {multiplier} #####")

    try:
        total_emission = float(activity_amount) * float(emission_factor) * float(multiplier)

        # 수식 문자열 생성 (multiplier 가 1.0 이 아닐 때만 표시)
        calc_formula = f"{activity_amount} {unit} × {emission_factor}"
        if float(multiplier) != 1.0:
            calc_formula += f" × {multiplier} (배수/인원)"

        return (f"✅ 계산완료:\n"
                f"- 수식: {calc_formula}\n"
                f"- 🌍 산출된 탄소 배출량: **{total_emission:.4f} kg CO2e**")
    except Exception as e:
        return f"계산 중 오류가 발생했습니다. : {str(e)}"