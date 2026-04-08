from langchain_core.tools import tool


@tool
def calculate_carbon_emission(electricity_kwh: float) -> str:
    """
    사용자가 구체적인 전력 사용량 숫자(kWh)를 제시했을 때만 호출한다.
    입력된 kWh 값에 한국 배출계수를 곱해 탄소 배출량(kgCO2)을 계산한다.
    """

    print("##### CARBON TOOL #####")

    # 한국 전력 배출계수: 0.4567 kgCO2/kWh (2022년 기준)
    emission_factor = 0.4567
    result = electricity_kwh * emission_factor
    return f"전력 사용량 {electricity_kwh} kWh → 탄소 배출량 {result:.2f} kgCO2"
