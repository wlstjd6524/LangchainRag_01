from typing import Union
from langchain_core.tools import tool


@tool
def calculate_carbon_emission(electricity_kwh: Union[float, list[float]]) -> str:
    """
    사용자가 구체적인 전력 사용량 숫자(kWh)를 제시했을 때만 호출한다.
    입력된 kWh 값에 한국 배출계수를 곱해 탄소 배출량(kgCO2)을 계산한다.
    단일 값(float) 또는 여러 값의 리스트(list[float]) 모두 처리 가능하며,
    CSV 데이터처럼 여러 값이 있을 경우 리스트로 한 번에 전달하여 1회만 호출한다.

    Args:
        electricity_kwh: 전력 사용량 (kWh 단위). 단일 값 또는 리스트.

    Returns:
        탄소 배출량 계산 결과 문자열
    """

    print("##### CARBON TOOL #####")

    # 한국 전력 배출계수: 0.4567 kgCO2/kWh (2022년 기준)
    emission_factor = 0.4567

    if isinstance(electricity_kwh, list):
        lines = []
        total_kwh = 0.0
        total_co2 = 0.0
        for i, kwh in enumerate(electricity_kwh, 1):
            co2 = kwh * emission_factor
            total_kwh += kwh
            total_co2 += co2
            lines.append(f"  {i}행: {kwh} kWh → {co2:.2f} kgCO2")
        lines.append(f"\n  합계: {total_kwh} kWh → {total_co2:.2f} kgCO2")
        return "[탄소 배출량 계산 결과]\n" + "\n".join(lines)
    else:
        result = electricity_kwh * emission_factor
        return f"전력 사용량 {electricity_kwh} kWh → 탄소 배출량 {result:.2f} kgCO2"
