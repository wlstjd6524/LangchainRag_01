"""
calculate_employee_kpi.py
임직원 다양성 KPI 계산 툴

[법적 근거 및 ESG 기준]
- 성별 비율: K-ESG S-3-1 | GRI 405-1
- 연령대 비율: GRI 405-1 | 고령자고용촉진법 시행령 제3조 | 청년고용촉진특별법 제5조
- 장애인 고용: 장애인고용촉진 및 직업재활법 제28조 제1항 | K-ESG S-3-3
- 정규직 비율: 기간제법 | K-ESG S-2-2 | 2025년 고용형태공시 결과(고용노동부)

[사용 전제]
csv_loader.py의 load_csv_data()로 CSV를 파싱한 뒤,
반환된 data 리스트를 employees 파라미터에 직접 전달합니다.
"""

import json
from langchain_core.tools import tool


# 법령/고시 기준 상수 (RAG 연동 시 이 부분만 교체)
CONSTANTS = {
    "disability_mandatory_rate": 3.1,   # 장애인고용촉진법 제28조 (민간기업 의무고용률)
    "regular_industry_avg": 72.6,       # 2025 고용형태공시 정규직 전체 평균 (고용노동부)
}


# K-ESG 점수 헬퍼
def _kesg_stage(value: float, thresholds: list[float], reverse: bool = False) -> int:
    """
    K-ESG 단계 판정
    reverse=False: 값이 클수록 높은 단계 (장애인고용률, 정규직 비율)
    reverse=True: 값이 작을수록 높은 단계 (성별 격차 — 격차가 작아야 좋음)
    """
    if reverse:
        value = 100 - value
    for stage, threshold in enumerate(thresholds, start=1):
        if value < threshold:
            return stage
    return len(thresholds) + 1


def _kesg_score(stage: int, max_stage: int = 5) -> int:
    """K-ESG 단계 → 점수 환산 (5단계: 0/25/50/75/100, 4단계: 0/33/66/100)"""
    score_map = {
        5: {1: 0, 2: 25, 3: 50, 4: 75,  5: 100},
        4: {1: 0, 2: 33, 3: 66, 4: 100},
    }
    return score_map.get(max_stage, score_map[5]).get(stage, 0)



# 내부 계산 함수 (_calc_*)
def _calc_gender(employees: list[dict]) -> dict:
    """
    성별 비율 계산 (K-ESG S-3-1 | GRI 405-1)

    [수식]
    여성 비율(%) = 여성 수 / 전체 수 × 100
    K-ESG 격차 = |전체 여성비율 - 관리자 여성비율|  →  격차가 작을수록 고득점
    """
    def _ratio(group: list[dict]) -> dict:
        n = len(group)
        if n == 0:
            return {"male": 0, "female": 0, "male_rate": 0.0, "female_rate": 0.0}
        male = sum(1 for e in group if e.get("gender") == "M")
        female = n - male
        return {
            "male": male, "female": female,
            "male_rate": round(male / n * 100, 1),
            "female_rate": round(female / n * 100, 1),
        }

    managers = [e for e in employees if e.get("position_level") in ("manager", "executive")]
    board = [e for e in employees if e.get("is_board_member")]

    total_r = _ratio(employees)
    manager_r = _ratio(managers)

    gap = abs(total_r["female_rate"] - manager_r["female_rate"])
    stage = _kesg_stage(gap, [20, 40, 60, 80], reverse=True)

    return {
        "전체 직원": total_r,
        "관리자": manager_r,
        "이사회": _ratio(board),
        "kesg_gap(전체-관리자 여성비율 격차)": round(gap, 1),
        "kesg_stage": stage,
        "kesg_score": _kesg_score(stage),
    }


def _calc_age(employees: list[dict]) -> dict:
    """
    연령대별 비율 계산 (GRI 405-1 | 고령자고용촉진법 시행령 제3조)

    [수식]
    연령대 비율(%) = 해당 연령대 인원 / 전체 인원 × 100
    GRI 기준: ~29세 / 30~49세 / 50세 이상
    국내법 기준: ~29세 / 30~54세 / 55세 이상
    """
    total = len(employees)

    def _group(min_age: int, max_age: int) -> dict:
        n = sum(1 for e in employees if min_age <= int(e.get("age", 0)) < max_age)
        return {"count": n, "rate": round(n / total * 100, 1)}

    return {
        "GRI 405-1 기준": {
            "30세 미만": _group(0,  30),
            "30~49세": _group(30, 50),
            "50세 이상": _group(50, 200),
        },
        "국내법 기준 (고령자고용촉진법)": {
            "30세 미만": _group(0,  30),
            "30~54세": _group(30, 55),
            "55세 이상": _group(55, 200),
        },
    }


def _calc_disability(employees: list[dict]) -> dict:
    """
    장애인 고용률 계산 (K-ESG S-3-3 | 장애인고용촉진법 제28조)

    [수식]
    실질 장애인 수 = 일반장애인 × 1 + 중증장애인 × 2  (장애인고용촉진법 시행령)
    장애인 고용률(%) = 실질 장애인 수 / 전체 인원 × 100
    달성률(%) = 장애인 고용률 / 의무고용률(3.1%) × 100
    """
    total = len(employees)
    effective = sum(
        2 if e.get("is_severe_disabled") else 1
        for e in employees if e.get("is_disabled")
    )
    actual_rate = round(effective / total * 100, 2)
    mandatory_rate = CONSTANTS["disability_mandatory_rate"]
    achievement = round(actual_rate / mandatory_rate * 100, 1)

    stage = _kesg_stage(achievement, [60, 80, 100, 120])

    return {
        "전체 직원 수": total,
        "실질 장애인 산정 수": effective,
        "장애인 고용률": f"{actual_rate}%",
        "의무고용률": f"{mandatory_rate}%",
        "달성률": f"{achievement}%",
        "kesg_stage": stage,
        "kesg_score": _kesg_score(stage),
        "준수 여부": "✅ 충족" if actual_rate >= mandatory_rate else "❌ 미충족",
    }


def _calc_employment_type(employees: list[dict]) -> dict:
    """
    고용형태별 비율 계산 (K-ESG S-2-2 | 기간제법)

    [수식]
    정규직 비율(%) = 정규직 수 / 전체 수 × 100
    업종 평균 대비 = 정규직 비율 - 업종 평균(72.6%)  (2025 고용형태공시, 고용노동부)
    """
    total  = len(employees)
    counts = {
        "정규직": sum(1 for e in employees if e.get("employment_type") == "regular"),
        "단시간": sum(1 for e in employees if e.get("employment_type") == "part_time"),
        "소속외": sum(1 for e in employees if e.get("employment_type") == "outsource"),
        "파견": sum(1 for e in employees if e.get("employment_type") == "dispatch"),
    }
    regular_rate = round(counts["정규직"] / total * 100, 1)
    industry_avg = CONSTANTS["regular_industry_avg"]
    vs_industry = round(regular_rate - industry_avg, 1)

    stage = _kesg_stage(regular_rate, [40, 60, 80])

    return {
        "전체 직원 수": total,
        "고용형태별 인원": counts,
        "정규직 비율": f"{regular_rate}%",
        "업종 평균 정규직률": f"{industry_avg}% (2025 고용형태공시)",
        "업종 평균 대비": f"{'+' if vs_industry >= 0 else ''}{vs_industry}%",
        "kesg_stage": stage,
        "kesg_score": _kesg_score(stage, max_stage=4),
    }


def _to_markdown(results: dict) -> str:
    """계산 결과 dict → Markdown 문자열 (범용 재귀 변환)"""

    METRIC_TITLE = {
        "gender": "성별 비율 (K-ESG S-3-1 | GRI 405-1)",
        "age": "연령대별 비율 (GRI 405-1 | 고령자고용촉진법)",
        "disability": "장애인 고용률 (K-ESG S-3-3 | 장애인고용촉진법)",
        "employment_type": "고용형태별 비율 (K-ESG S-2-2 | 기간제법)",
    }

    def _render(data, depth=3) -> str:
        """dict/기타 값을 재귀적으로 Markdown으로 변환"""
        if isinstance(data, dict):
            lines = []
            for k, v in data.items():
                if isinstance(v, dict):
                    lines.append(f"{'#' * depth} {k}\n")
                    lines.append(_render(v, depth + 1))
                else:
                    lines.append(f"- **{k}:** {v}")
            return "\n".join(lines)
        return str(data)

    sections = ["# 임직원 다양성 KPI 분석 결과\n"]
    for metric, data in results.items():
        title = METRIC_TITLE.get(metric, metric)
        section = [f"## {title}\n"]
        if isinstance(data, dict) and "error" in data:
            section.append(f"⚠️ 오류: {data['error']}")
        else:
            section.append(_render(data))
        sections.append("\n".join(section))

    return "\n\n---\n\n".join(sections)

_METRIC_MAP = {
    "gender": _calc_gender,
    "age": _calc_age,
    "disability": _calc_disability,
    "employment_type": _calc_employment_type,
}

@tool
def calculate_employee_kpi(employees: list[dict], metrics: list[str]) -> str:
    """
    직원 데이터로 요청된 ESG 인사 지표(KPI)를 계산한다.
    csv_loader의 load_csv_data()로 데이터를 먼저 파싱한 뒤 이 툴을 호출한다.

    사용자가 임직원 다양성, 성별·연령·장애인·고용형태 관련 ESG 지표를 요청할 때 호출한다.

    Args:
        employees: load_csv_data()가 반환한 data 리스트 (list[dict])

        metrics: 계산할 지표 목록. 다음 중 하나 이상 선택.
            - "gender": 성별 비율 및 K-ESG S-3-1 점수 (GRI 405-1)
            - "age": 연령대별 비율 (GRI 405-1 / 고령자고용촉진법)
            - "disability": 장애인 고용률 및 K-ESG S-3-3 점수
            - "employment_type": 고용형태별 비율 및 K-ESG S-2-2 점수

    Returns:
        요청된 지표의 계산 결과 마크다운 문자열
    """
    print("##### EMPLOYEE KPI TOOL #####")
    print(f"##### metrics: {metrics} #####")

    if isinstance(employees, str):
        try:
            parsed = json.loads(employees)
            employees = parsed.get("data", [])
        except (json.JSONDecodeError, AttributeError):
            return "오류: 직원 데이터 파싱 실패. CSV 파싱 결과의 직원 데이터 목록을 확인하세요."
        
    if not employees:
        return "오류: 직원 데이터가 없습니다. load_csv_data()를 먼저 호출하세요."

    unknown = [m for m in metrics if m not in _METRIC_MAP]
    if unknown:
        return f"오류: 지원하지 않는 지표 → {unknown}\n지원 목록: {sorted(_METRIC_MAP)}"

    results = {}
    for metric in metrics:
        try:
            results[metric] = _METRIC_MAP[metric](employees)
        except Exception as e:
            results[metric] = {"error": str(e)}

    return _to_markdown(results)