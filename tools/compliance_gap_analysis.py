import json
from tools.calculate_employee_kpi import _calc_gender, _calc_disability, _calc_employment_type
from tools.score_ethics_risk import CHECKLIST
from langchain_core.tools import tool

# 기준값 정의
# 안전 지표
SAFETY_BENCHMARKS = {
    "kesg_code": "S-4-2",
    "name": "산업재해율",
    "방식": "전년 대비 개선 여부",
    "법적의무": True,        # 법률에 직접적인 근거가 있을 경우 또는 명시적인 의무인 경우에만 True, 나머지는 False
    "법적근거": "중대재해처벌등에관한법률",
    "판정기준": {
        # K-ESG S-4-2 3단계 기준 반영
        "3단계(양호)": "LTIR/TRIR 감소 추세",
        "2단계(보통)": "LTIR/TRIR 변동 없음",
        "1단계(미흡)": "LTIR/TRIR 증가 추세"
    },
    # 단년도 데이터만 있을 경우
    "단년도_참고_출처": "고용노동부 산업재해현황분석 > https://www.moel.go.kr",
    "단년도_주의": "데이터 미확인 - 업종별 직접 확인 필요",
}

# 탄소 배출
CARBON_BENCHMARKS = {
    "kesg_code": "E-3-1",
    "name": "온실가스 배출량 (Scope1 & Scope2)",
    "방식": "추세",
    "법적의무": False,  # 배출권거래제 할당 대상 기업만 법적 의무
    "법적근거": "온실가스배출권의 할당 및 거래에 관한 법률",
    "판정기준": {
        "3단계(양호)": "온실가스 배출량 감축 추세",
        "2단계(보통)": "온실가스 배출량 변동 없음",
        "1단계(미흡)": "온실가스 배출량 증가 추세",
    },
    "배출계수_현황": "한국 배출계수: 0.4567 kgCO2/kWh (2022년 기준)",
    "배출계수_참고_출처": "온실가스종합정보센터 > https://www.gir.go.kr",
    "배출계수_주의": "최신 연도 계수 확인 필요 - 연도별 변동 가능"
}

# 용수 및 폐기물
WATER_WASTE_BENCHMARKS = {
    "용수": {
        "kesg_code": "E-5-2",
        "name": "재사용 용수 비율",
        "방식": "추세",
        "계산식": "재사용 용수 비율 = 총 재사용 용수량 / 총 용수 사용량",
        "법적의무": True,
        "법적근거": "물의 재이용 촉진 및 지원에 관한 법률",
        "법적_활동기준": {
            "시설1": "빗물이용시설",
            "시설2": "중수도",
            "시설3": "하·폐수처리수 재이용시설 및 온배수 재이용시설",
            "시설4": "물 재이용수 활용시설 (물 재이용수를 외부 공급받아 공업용수로 활용하는 시설에 한정)"
        },
        "법적_인정기준": {
            "빗물이용시설": "「물의 재이용 촉진 및 지원에 관한 법률 시행규칙」 제4조 시설·관리기준 준수 (단, 법 제8조 의무설치 대상이 아닌 경우 시행규칙 제4조제1항제3호 가목 빗물 저류조 용량기준 적용 제외)",
            "중수도": "「물의 재이용 촉진 및 지원에 관한 법률 시행규칙」 제7조 시설·관리기준과 [별표 1]에 따른 수질기준 모두 준수",
            "하·폐수처리수 재이용시설": "「물의 재이용 촉진 및 지원에 관한 법률 시행령」 제16조 설치기준과 시행규칙 [별표 2]에 따른 수질기준 모두 준수",
            "물 재이용수 활용시설": "목표 재이용률을 수립하고 이행",
        },
        "판정기준": {
            "3단계(양호)": "재사용 용수 비율 증가 추세",
            "2단계(보통)": "재사용 용수 비율 변동 없음",
            "1단계(미흡)": "재사용 용수 비율 감소 추세"
        },
        "점수": {"1단계": 0, "2단계": 50, "3단계": 100},
        "특이사항": {
            "0점_조건":   "용수를 전혀 재사용하지 않는 경우",
            "100점_조건": "국내외 모든 사업장이 폐수무방류시스템을 구축하거나, 목표 재이용률을 수립하고 완전 이행한 경우",
            "재사용_정의": "직접재사용(Direct Reuse)만 해당 — 방류 후 재취수하는 간접재사용(Indirect Reuse)은 제외",
            "데이터_기간": "최근 4개회계연도 (3개년 이하 보유 시 해당 데이터로 추세 산정)",
        },
    },
    "폐기물": {
        "kesg_code": "E-6-2",
        "name": "폐기물 재활용 비율",
        "방식": "추세",
        "계산식": "폐기물 재활용 비율 = 폐기물 재활용량(재사용 포함) / 재활용 대상 폐기물 발생량",
        "법적의무": False,
        "법적근거": "폐기물관리법",
        "판정기준": {
            "3단계(양호)": "폐기물 재활용 비율 증가 추세",
            "2단계(보통)": "폐기물 재활용 비율 변동 없음",
            "1단계(미흡)": "폐기물 재활용 비율 감소 추세",
        },
        "점수": {"1단계": 0, "2단계": 50, "3단계": 100},
        "특이사항": {
            "0점_조건":   "재활용을 전혀 하지 않거나 데이터 미관리",
            "100점_조건": "국내외 모든 사업장이 재활용·재사용 가능한 폐기물 전부를 재활용·재사용",
            "데이터_기간": "최근 4개회계연도",
        },
    }
}

def _check_employee_kpi(employees: list[dict]) -> list[dict]:
    # str로 들어온 경우 자동 파싱
    if isinstance(employees, str):
        try:
            parsed = json.loads(employees)
            employees = parsed.get("data", [])
        except (json.JSONDecodeError, AttributeError):
            return [{
                "kesg_code": "S-KPI",
                "name": "임직원 KPI 전체",
                "갭여부": None,
                "경고": "데이터 미확인 — JSON 파싱 실패. load_csv_data 결과의 data 필드를 확인하세요.",
                "법적의무": False,
            }]
        
    if not employees:
        return [{
            "kesg_code": "S-KPI",
            "name": "임직원 KPI 전체",
            "갭여부": None,
            "경고": "데이터 미확인 — 직원 데이터가 없습니다",
            "법적의무": False,
        }]
    
    results = []

    # S-3-1 여성 관리자 비율
    gender = _calc_gender(employees)
    results.append({
        "kesg_code": "S-3-1",
        "name": "여성 관리자 비율",
        "kesg_stage": gender["kesg_stage"],
        "kesg_score": gender["kesg_score"],
        "갭여부": gender["kesg_stage"] < 3,   # 3단계 미만 = 갭
        "법적의무": False,
        "출처": "K-ESG S-3-1 | GRI 405-1",
    })

    # S-3-3 장애인 고용률
    disability = _calc_disability(employees)
    results.append({
        "kesg_code": "S-3-3",
        "name": "장애인 고용률",
        "kesg_stage": disability["kesg_stage"],
        "kesg_score": disability["kesg_score"],
        "갭여부": "미충족" in disability["준수 여부"],
        "법적의무": True,
        "출처": "K-ESG S-3-3 | 장애인고용촉진법 제28조",
    })

    # S-2-2 정규직 비율
    employment = _calc_employment_type(employees)
    results.append({
        "kesg_code": "S-2-2",
        "name": "정규직 비율",
        "kesg_stage": employment["kesg_stage"],
        "kesg_score": employment["kesg_score"],
        "갭여부": employment["kesg_stage"] < 3,
        "법적의무": False,
        "출처": "K-ESG S-2-2 | 기간제법",
    })

    return results

def _check_ethics(responses: dict[str, bool]) -> dict:
    total_score = sum(
        item["weight"] for item in CHECKLIST
        if responses.get(item["id"], False)
    )
    # RISK_GRADE 경계: 80↑ LOW, 60~79 MEDIUM, 40~59 HIGH, ~39 CRITICAL
    if total_score >= 80:
        risk_label = "LOW"
    elif total_score >= 60:
        risk_label = "MEDIUM"
    elif total_score >= 40:
        risk_label = "HIGH"
    else:
        risk_label = "CRITICAL"

    return {
        "kesg_code": "G-4-1",
        "name": "윤리규범 운영",
        "total_score": total_score,
        "risk_label": risk_label,
        "갭여부": risk_label in ("HIGH", "CRITICAL"),
        "법적의무": False,
        "출처": "K-ESG G-4-1 | GRI 2-26",
    }

def _check_safety(ltir_history: list[float]) -> dict:
    """
    Args:
        ltir_history: 연도 오름차순 LTIR 값 리스트 (예: [0.8, 0.7, 0.6, 0.5])
                      최소 2개년 이상 필요. 1개년만 있으면 판정 불가.
    """
    if len(ltir_history) < 2:
        return {
            "kesg_code": "S-4-2",
            "name": "산업재해율 (LTIR)",
            "갭여부": None,
            "경고": "데이터 미확인 — 최소 2개년 데이터 필요 (K-ESG S-4-2는 4개년 추세 기준)",
            "법적의무": True,
            "출처": "K-ESG S-4-2 | 중대재해처벌등에관한법률",
        }

    # 추세 판정: 마지막 값이 첫 값보다 낮으면 감소 추세
    trend = ltir_history[-1] - ltir_history[0]

    if trend < 0:
        kesg_stage, 갭여부 = 3, False   # 감소 추세 = 양호
    elif trend == 0:
        kesg_stage, 갭여부 = 2, True    # 변동 없음 = 보통 (개선 필요)
    else:
        kesg_stage, 갭여부 = 1, True    # 증가 추세 = 미흡

    return {
        "kesg_code": "S-4-2",
        "name": "산업재해율 (LTIR)",
        "kesg_stage": kesg_stage,
        "추세": "감소" if trend < 0 else ("유지" if trend == 0 else "증가"),
        "갭여부": 갭여부,
        "법적의무": True,
        "출처": "K-ESG S-4-2 | 중대재해처벌등에관한법률",
    }

def _check_carbon(emission_history: list[float]) -> dict:
    """
    Args:
        emission_history: 연도 오름차순 원단위 온실가스 배출량 리스트
                          (단위: tCO2e / 매출액 또는 생산량 원단위)
    """
    if len(emission_history) < 2:
        return {
            "kesg_code": "E-3-1",
            "name": "온실가스 배출량 (Scope1 & Scope2)",
            "갭여부": None,
            "경고": "데이터 미확인 — 최소 2개년 데이터 필요",
            "법적의무": False,
            "출처": "K-ESG E-3-1 | GRI 305",
        }

    trend = emission_history[-1] - emission_history[0]

    if trend < 0:
        kesg_stage, 갭여부 = 3, False
    elif trend == 0:
        kesg_stage, 갭여부 = 2, True
    else:
        kesg_stage, 갭여부 = 1, True

    return {
        "kesg_code": "E-3-1",
        "name": "온실가스 배출량 (Scope1 & Scope2)",
        "kesg_stage": kesg_stage,
        "추세": "감소" if trend < 0 else ("유지" if trend == 0 else "증가"),
        "갭여부": 갭여부,
        "법적의무": False,
        "출처": "K-ESG E-3-1 | GRI 305",
    }

def _check_water(
    water_rate_history: list[float],   # 용수 재사용 비율 연도별 리스트
    waste_rate_history: list[float],   # 폐기물 재활용 비율 연도별 리스트
) -> list[dict]:
    """
    K-ESG E-5-2 (용수), E-6-2 (폐기물) 추세 판정
    """
    results = []

    for history, kesg_code, name in [
        (water_rate_history, "E-5-2", "재사용 용수 비율"),
        (waste_rate_history, "E-6-2", "폐기물 재활용 비율"),
    ]:
        WATER_LEGAL = {"E-5-2": True, "E-6-2": False}

        if len(history) < 2:
            results.append({
                "kesg_code": kesg_code,
                "name": name,
                "갭여부": None,
                "경고": "데이터 미확인 — 최소 2개년 데이터 필요",
                "법적의무": WATER_LEGAL[kesg_code],
            })
            continue

        trend = history[-1] - history[0]

        results.append({
            "kesg_code": kesg_code,
            "name": name,
            "kesg_stage": 3 if trend > 0 else (2 if trend == 0 else 1),
            # 용수/폐기물은 비율이 증가해야 좋으므로 방향 반전
            "추세": "증가(양호)" if trend > 0 else ("유지" if trend == 0 else "감소(미흡)"),
            "갭여부": trend <= 0,   # 증가 추세일 때만 갭 없음
            "법적의무": WATER_LEGAL[kesg_code],
            "출처": f"K-ESG {kesg_code}",
        })

    return results

def _prioritize(gap_items: list[dict]) -> list[dict]:
    """
    갭 있는 항목만 필터링 후 우선순위 정렬
    기준: ① 법적의무 True 우선  ② kesg_stage 낮은 순 (점수 낮을수록 시급)
    """
    gaps = [item for item in gap_items if item.get("갭여부") is True]
    return sorted(
        gaps,
        key=lambda x: (
            not x.get("법적의무", False),  # True(법적의무)가 앞으로
            x.get("kesg_stage", 99),      # 단계 낮을수록 앞으로
        )
    )


def _to_markdown(gap_items: list[dict], prioritized: list[dict]) -> str:
    """전체 갭 분석 결과를 Markdown 리포트로 변환"""
    lines = ["## ESG 컴플라이언스 갭 분석 결과\n"]

    # 전체 항목 현황 테이블
    lines.append("### 항목별 현황\n")
    lines.append("| K-ESG 코드 | 항목명 | 단계 | 갭 여부 | 법적의무 |")
    lines.append("|---|---|---|---|---|")
    for item in gap_items:
        stage = item.get("kesg_stage", item.get("risk_label", "N/A"))
        갭_여부 = item.get("갭여부")
        if 갭_여부 is True:
            갭 = "❌ 미충족"
        elif 갭_여부 is False:
            갭 = "✅ 충족"
        else:
            갭 = "⚠️ 데이터 부족"
        법적 = "⚖️ 법적의무" if item.get("법적의무") else "📌 권고"
        lines.append(f"| {item['kesg_code']} | {item['name']} | {stage} | {갭} | {법적} |")

    # 우선순위 개선 권고
    lines.append("\n### 개선 권고 (우선순위 순)\n")
    if not prioritized:
        lines.append("모든 항목을 충족하고 있습니다.")
    else:
        for i, item in enumerate(prioritized, 1):
            법적태그 = "⚖️ 법적 의무" if item.get("법적의무") else "📌 권고"
            lines.append(f"{i}. **[{item['kesg_code']}] {item['name']}** — {법적태그}")
            if "출처" in item:
                lines.append(f"   - 근거: {item['출처']}")

    return "\n".join(lines)


@tool
def compliance_gap_analysis(tool_outputs: dict) -> str:
    """
    ESG 전 영역(E/S/G) 컴플라이언스 갭을 통합 분석한다.
    각 계산 툴의 결과를 입력받아, K-ESG 기준 대비 미충족 항목과 개선 우선순위를 반환한다.

    Args:
        tool_outputs: 각 툴 결과를 담은 딕셔너리. 예:
            {
              "employees": [...],                # calculate_employee_kpi용
              "ethics_responses": {...},         # score_ethics_risk용
              "ltir_history": [0.8, 0.6],        # calculate_safety용 (연도 오름차순)
              "emission_history": [120, 110],    # calculate_carbon용 (원단위)
              "water_rate_history": [30, 35],    # water_recycling용
              "waste_rate_history": [45, 50],    # water_recycling용
            }
    """
    print("##### COMPLIANCE GAP ANALYSIS TOOL #####")

    all_items = []

    if "employees" in tool_outputs:
        all_items.extend(_check_employee_kpi(tool_outputs["employees"]))

    if "ethics_responses" in tool_outputs:
        all_items.append(_check_ethics(tool_outputs["ethics_responses"]))

    if "ltir_history" in tool_outputs:
        all_items.append(_check_safety(tool_outputs["ltir_history"]))

    if "emission_history" in tool_outputs:
        all_items.append(_check_carbon(tool_outputs["emission_history"]))

    if "water_rate_history" in tool_outputs or "waste_rate_history" in tool_outputs:
        all_items.extend(_check_water(
            tool_outputs.get("water_rate_history", []),
            tool_outputs.get("waste_rate_history", []),
        ))

    prioritized = _prioritize(all_items)
    return _to_markdown(all_items, prioritized)
