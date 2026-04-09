"""
employee_kpi_calculate.py
임직원 다양성 및 KPI 달성률 계산 툴

[법적 근거 및 ESG 기준]
- 성별 비율   : K-ESG S-3-1 | GRI 405-1
- 연령대 비율 : GRI 405-1 | 고령자고용촉진법 시행령 제3조 | 청년고용촉진특별법 제5조
- 장애인 고용 : 장애인고용촉진 및 직업재활법 제28조 제1항 | K-ESG S-3-3
- 정규직 비율 : 기간제법 | K-ESG S-2-2 | 2025년 고용형태공시 결과(고용노동부)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

# 동적 조회
class ConstantProvider:
    """
    법령/고시 기준값을 RAG 또는 Web Search를 통해 동적으로 조회하는 클래스
    조회 실패 시 하드코딩된 fallback 값을 사용하여 안정성 보장
    """

    # fallback 값 (RAG 또는 Web Search 실패 시에만 사용)
    _FALLBACK = {
        "disability_mandatory_rate": 3.1,      # 장애인고용촉진법 제28조
        "regular_industry_avg": 72.6,          # 정규직 전체 평균 (2025년 고용형태공시)
        "parttime_industry_avg": 8.8,          # 기간제 전체 평균 (2025년 고용형태공시)
        "outsource_industry_avg": 16.3,        # 소속외 전체 평균 (2025년 고용형태공시)
        "age_young_max": 30,
        "age_middle_max_gri": 50,              # GRI 405-1 기준 중년층 최대 연령
        "age_senior_kr": 55,                   # 한국 기준 고령자 연령 기준
    }

    def __init__(self, rag_client=None, web_search_client=None):
        self.rag = rag_client                    # RAG 클라이언트 인스턴스
        self.web_search = web_search_client      # Web Search 클라이언트 인스턴스
        self._cache = {}                         # 중복 조회 방지용 캐시

    def get(self, key:str) -> float:
        """
        우선순위: 캐시 -> RAG -> Web Search -> Fallback
        """
        if key in self._cache:
            return self._cache[key]
        
        value = (
            self._from_rag(key)
            or self._from_web_search(key)
            or self._FALLBACK.get(key)
        )

        self._cache[key] = value
        return value
    
    def _from_rag(self, key:str) -> float | None:
        if self.rag is None:
            return None
        try:
            query = self._build_rag_query(key)
            result = self.rag.query(query)
            return self._parse_numeric(result)
        except Exception as e:
            print(f"[ConstantProvider] RAG 조회 실패 ({key}): {e}")
            return None
        
    def _from_web_search(self, key:str) -> float | None:
        if self.web_search is None:
            return None
        try:
            query = self._build_web_search_query(key)
            result = self.web_search.search(query)
            return self._parse_numeric(result)
        except Exception as e:
            print(f"[ConstantProvider] Web Search 조회 실패 ({key}): {e}")
            return None
        
    def _build_rag_query(self, key:str) -> str:
        """key별 RAG 검색 쿼리 맵핑"""
        query_map = {
            "disability_mandatory_rate": "민간기업 장애인 의무고용률(장애인고용촉진법)",
            "regular_industry_avg": "정규직 근로자 비율(2025년 고용형태공시)",
            "parttime_industry_avg": "단시간 근로자 비율(2025년 고용형태공시)",
            "outsource_industry_avg": "소속외 근로자 비율(2025년 고용형태공시)",
            }
        return query_map.get(key, key)
    
    def _build_web_search_query(self, key:str) -> str:
        """key별 Web Search 검색 쿼리 맵핑"""
        query_map = {
            "disability_mandatory_rate": "한국 민간기업 장애인 의무고용률 최신 장애인고용촉진법 고용노동부",
            "regular_industry_avg": "정규직 근로자 비율 최신 고용형태고시",
            "parttime_industry_avg": "단시간 근로자 비율 최신 고용형태고시",
            "outsource_industry_avg": "소속외 근로자 비율 최신 고용형태고시",
        }
        return query_map.get(key, key)
    
    @staticmethod
    def _parse_numeric(raw: str | dict) -> float | None:
        """
        RAG/Web Search 결과에서 숫자만 추출하여 float로 반환
        결과 형태는 클라이언트 스펙에 따라 조정 필요
        """
        import re
        text = raw if isinstance(raw, str) else str(raw)
        match = re.search(r"\d+\.?\d*", text)
        return float(match.group()) if match else None
    

# 데이터 클래스 - 입력 스키마
@dataclass
class Employee:
    id: str
    gender: Literal["M", "F"]
    age: int
    employment_type: Literal["regular", "part_time", "outsource", "dispatch"]
    position_level: Literal["staff", "manager", "executive"]
    is_board_member: bool = False
    is_disabled: bool = False
    is_severe_disabled: bool = False   # 중증장애인 여부 (K-ESG S-3-3 기준)

@dataclass
class DiversityInput:
    company_name: str
    fiscal_year: int
    employees: list[Employee] = field(default_factory=list)
    industry_avg_female_ratio: float = 0.0       # 업종 평균 여성 비율


class EmployeeKPITool:

    def __init__(self, data: DiversityInput, rag_client=None, web_search_client=None):
        self.data = data
        self.constants = ConstantProvider(rag_client=rag_client, web_search_client=web_search_client)


    # 성별 비율 계산
    def calculate_gender_ratio(self) -> dict:
        emps = self.data.employees
        total = len(emps)
        if total == 0:
            return {}
        
        def ratio(group: list) -> dict:
            """직원 리스트를 받아서 남/여 수와 비율을 반환하는 내부 함수"""
            if not group:
                return {"male": 0, "female": 0,
                        "male_rate": 0.0, "female_rate": 0.0}
            male = sum(1 for e in group if e.gender == "M")
            female = sum(1 for e in group if e.gender == "F")
            n = len(group)
            return {
                "male": male,
                "female": female,
                "male_rate": round(male / n * 100, 1),
                "female_rate": round(female / n * 100, 1),
            }
        
        
        # 집단별 필터링
        managers = [e for e in emps if e.position_level in ("manager", "executive")]
        board = [e for e in emps if e.is_board_member]
        regulars = [e for e in emps if e.employment_type == "regular"]
        contracts = [e for e in emps if e.employment_type != "regular"]

        result = {
            "total": ratio(emps),           # 전체 직원 성별 비율
            "managers": ratio(managers),    # 관리자(과장급 이상)
            "board": ratio(board),          # 이사회 구성원 
            "regulars": ratio(regulars),    # 정규직 
            "contracts": ratio(contracts),  # 비정규직
        }

        # K-ESG S-3-1: 전체 여성비율 vs 미등기임원 여성비율 차이
        gap = abs(result["total"]["female_rate"] - result["managers"]["female_rate"])
        result["kesg_gap"] = round(gap, 1)
        result["kesg_stage"] = self._get_kesg_stage(gap, [20, 40, 60, 80], reverse=True)
        result["kesg_score"] = self._get_kesg_score(result["kesg_stage"])
        return result
    

    # 연령대별 비율 계산
    def calculate_age_ratio(self) -> dict:
        emps = self.data.employees
        total = len(emps)
        if total == 0:
            return {}
        
        def age_group(min_age: int, max_age: int) -> dict:
            """min_age 이상 max_age 미만인 인원 수와 비율 반환"""
            group = [e for e in emps if min_age <= e.age < max_age]
            n = len(group)
            return {"count": n, "rate": round(n / total * 100, 1)}
        
        return {
            # GRI 405-1 기준: 30 / 30~50 / 50 이상
            "gri_standard": {
                "under_30": age_group(0, 30),
                "30_to_50": age_group(30, 50),
                "over_50": age_group(50, 200),
            },
            # 국내법 기준(고령자고용촉진법 시행령 제3조): 30 / 30~55 / 55 이상
            "kr_standard": {
                "under_30": age_group(0, 30),
                "30_to_55": age_group(30, 55),
                "over_55": age_group(55, 200),
            },
        }
    

    # 장애인 고용률 계산
    def calculate_disability_ratio(self) -> dict:
        emps = self.data.employees
        total = len(emps)
        if total == 0:
            return {}
        
        # 중증장애인 2명으로 산정 (장애인고용촉진법 시행령)
        effective_count = sum(2 if e.is_severe_disabled else 1 for e in emps if e.is_disabled)
        actual_rate = round(effective_count / total * 100, 1)
        mandatory_rate = self.constants.get("disability_mandatory_rate")    # 3.1% (장애인고용촉진법 제28조)
        achievement = round(actual_rate / mandatory_rate * 100, 1)

        return {
            "actual_rate": str(actual_rate) + "%",
            "mandatory_rate": str(mandatory_rate) + "%",
            "achievement": str(achievement) + "%",
            "effective_count": str(effective_count) + "명",
            "kesg_achievement": self._get_kesg_stage(achievement, [60, 80, 100, 120]),
            "kesg_score": self._get_kesg_score(self._get_kesg_stage(achievement, [60, 80, 100, 120])),
        }
    


    # 정규직/비정규직 비율 계산
    def calculate_employment_type_ratio(self) -> dict:
        emps = self.data.employees
        total = len(emps)
        if total == 0:
            return {}
        
        # K-ESG S-2-2 공식: 정규직 = 전체 - 기간제 - 단시간 - 파견/용역
        type_counts = {
            "regular": sum(1 for e in emps if e.employment_type == "regular"),
            "part_time": sum(1 for e in emps if e.employment_type == "part_time"),
            "outsource": sum(1 for e in emps if e.employment_type == "outsource"),
            "dispatch": sum(1 for e in emps if e.employment_type == "dispatch"),
        }
        regular_rate = round(type_counts["regular"] / total * 100, 1)
        industry_avg = self.constants.get("regular_industry_avg")       # 업종별 평균
        vs_industry = round(regular_rate - industry_avg, 1)             # 업계 대비 차이

        return {
            "type_counts": type_counts,
            "regular_rate": str(regular_rate) + "%",
            "industry_avg": str(industry_avg) + "%",
            "vs_industry": str(vs_industry) + "%",     # 양수면 평균보다 높음, 음수면 낮음
            "kesg_achievement": self._get_kesg_stage(regular_rate, [40, 60, 80], reverse=False),
            "kesg_score": self._get_kesg_score(self._get_kesg_stage(regular_rate, [40, 60, 80]), max_stage=4),
        }


    # 내부 헬퍼 함수
    def _get_kesg_stage(self, value: float, thresholds: list, reverse: bool = False) -> int:
        """
        K-ESG 단계 판정 공통 함수
        reverse=False: 값이 클수록 높은 단계 (장애인고용률, 정규직 비율)
        reverse=True: 값이 작을수록 높은 단계 (성별 격차 - 격차가 작아야 좋음)
        """
        if reverse:
            value = 100 - value   # 방향 반전

        for stage, threshold in enumerate(thresholds, start=1):
            if value < threshold:
                return stage
            
        return len(thresholds) + 1   # 모든 임계값을 초과하면 가장 높은 단계 (최고 단계)
    

    def _get_kesg_score(self, stage: int, max_stage: int = 5) -> int:
        """
        K-ESG 단계 -> 점수 환산
        5단계: 0 / 25 / 50 / 75 / 100
        3단계: 0 / 50 / 100
        """
        if max_stage == 5:
            scores = {1: 0, 2: 25, 3: 50, 4: 75, 5: 100}
        else:
            scores = {1: 0, 2: 50, 3: 100}
        return scores.get(stage, 0)
    

# Langchain Tool 래핑 (agent.py에서 사용)
import csv
import os
from langchain_core.tools import tool

def _parse_employees_from_csv(csv_path: str) -> list[Employee] | str:
    """
    CSV 파일을 읽어 Employee 객체 리스트로 변환합니다.

    CSV 필수 컬럼:
        id, gender, age, employment_type, position_level
    CSV 선택 컬럼 (없으면 False로 처리):
        is_board_member, is_disabled, is_severe_disabled

    Args:
        csv_path (str): CSV 파일 절대/상대 경로

    Returns:
        list[Employee] | str: 성공 시 Employee 리스트, 실패 시 에러 메시지 문자열

    CSV 예시:
        id,gender,age,employment_type,position_level,is_board_member,is_disabled,is_severe_disabled
        001,M,35,regular,manager,False,False,False
        002,F,28,part_time,staff,False,True,False
    """
    REQUIRED_COLUMNS = {"id", "gender", "age", "employment_type", "position_level"}
    BOOL_COLUMNS = {"is_board_member", "is_disabled", "is_severe_disabled"}

    if not os.path.isfile(csv_path):
        return f"파일을 찾을 수 없습니다: {csv_path}"

    try:
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers = set(reader.fieldnames or [])

            missing = REQUIRED_COLUMNS - headers
            if missing:
                return (
                    f"CSV 필수 컬럼 누락: {sorted(missing)}\n"
                    f"필수 컬럼: {sorted(REQUIRED_COLUMNS)}"
                )

            employees = []
            for i, row in enumerate(reader, start=2):   # 헤더가 1행이므로 데이터는 2행부터
                try:
                    # bool 컬럼: "True"/"False"/"1"/"0" 모두 허용
                    bool_val = lambda col: str(row.get(col, "False")).strip().lower() in ("true", "1")

                    employees.append(Employee(
                        id=row["id"].strip(),
                        gender=row["gender"].strip().upper(),
                        age=int(row["age"]),
                        employment_type=row["employment_type"].strip(),
                        position_level=row["position_level"].strip(),
                        is_board_member=bool_val("is_board_member"),
                        is_disabled=bool_val("is_disabled"),
                        is_severe_disabled=bool_val("is_severe_disabled"),
                    ))
                except (ValueError, KeyError) as e:
                    return f"{i}행 데이터 오류: {e}\n해당 행: {dict(row)}"

        if not employees:
            return "CSV 파일에 데이터가 없습니다. (헤더만 존재)"

        return employees

    except UnicodeDecodeError:
        return "파일 인코딩 오류: UTF-8 또는 UTF-8 BOM 형식으로 저장해주세요."
    except Exception as e:
        return f"CSV 파싱 중 예외 발생: {e}"


def _build_tool_input_from_csv(
    csv_path: str,
    company_name: str = "company",
    fiscal_year: int = 2024,
) -> EmployeeKPITool | str:
    """
    CSV 파일 경로로 EmployeeKPITool 인스턴스를 생성합니다.

    Args:
        csv_path (str): 직원 데이터 CSV 파일 경로
        company_name (str): 회사명 (기본값: "company")
        fiscal_year (int): 회계연도 (기본값: 2024)

    Returns:
        EmployeeKPITool | str: 성공 시 Tool 인스턴스, 실패 시 에러 메시지
    """
    employees = _parse_employees_from_csv(csv_path)
    if isinstance(employees, str):
        return employees

    return EmployeeKPITool(
        DiversityInput(
            company_name=company_name,
            fiscal_year=fiscal_year,
            employees=employees,
        )
    )


@tool
def calculate_gender_ratio_tool(
    csv_path: str,
    company_name: str = "입력사",
    fiscal_year: int = 2024,
) -> str:
    """
    CSV 파일의 직원 데이터로 성별 비율 및 K-ESG S-3-1 점수를 계산합니다.

    Args:
        csv_path (str):
            직원 데이터 CSV 파일 경로.
            필수 컬럼: id, gender(M/F), age, employment_type, position_level
            선택 컬럼: is_board_member, is_disabled, is_severe_disabled

        company_name (str, optional):
            회사명. 기본값 "입력사".

        fiscal_year (int, optional):
            회계연도. 기본값 2024.

    Returns:
        str: 성별 비율 및 K-ESG 점수 계산 결과 (JSON 형식 문자열)

    출력 예시:
        {
          "total":     {"male": 70, "female": 30, "male_rate": 70.0, "female_rate": 30.0},
          "managers":  {"male": 15, "female":  5, "male_rate": 75.0, "female_rate": 25.0},
          "board":     {"male":  4, "female":  1, "male_rate": 80.0, "female_rate": 20.0},
          "regulars":  {"male": 60, "female": 20, "male_rate": 75.0, "female_rate": 25.0},
          "contracts": {"male": 10, "female": 10, "male_rate": 50.0, "female_rate": 50.0},
          "kesg_gap":   5.0,
          "kesg_stage": 4,
          "kesg_score": 75
        }

        kesg_gap: 전체 여성비율과 관리자 여성비율의 차이 (작을수록 우수)
        kesg_score: 0 / 25 / 50 / 75 / 100 중 하나
    """
    tool_instance = _build_tool_input_from_csv(csv_path, company_name, fiscal_year)
    if isinstance(tool_instance, str):
        return tool_instance
    return str(tool_instance.calculate_gender_ratio())


@tool
def calculate_age_ratio_tool(
    csv_path: str,
    company_name: str = "입력사",
    fiscal_year: int = 2024,
) -> str:
    """
    CSV 파일의 직원 데이터로 연령대별 비율을 계산합니다. (GRI 405-1 / 고령자고용촉진법)

    Args:
        csv_path (str):
            직원 데이터 CSV 파일 경로.
            필수 컬럼: id, gender, age, employment_type, position_level

        company_name (str, optional):
            회사명. 기본값 "입력사".

        fiscal_year (int, optional):
            회계연도. 기본값 2024.

    Returns:
        str: 연령대별 비율 계산 결과 (JSON 형식 문자열)

    출력 예시:
        {
          "gri_standard": {
            "under_30": {"count": 20, "rate": 20.0},
            "30_to_50": {"count": 60, "rate": 60.0},
            "over_50":  {"count": 20, "rate": 20.0}
          },
          "kr_standard": {
            "under_30": {"count": 20, "rate": 20.0},
            "30_to_55": {"count": 65, "rate": 65.0},
            "over_55":  {"count": 15, "rate": 15.0}
          }
        }

        gri_standard: GRI 405-1 기준 (30 / 30~50 / 50+)
        kr_standard:  고령자고용촉진법 기준 (30 / 30~55 / 55+)
    """
    tool_instance = _build_tool_input_from_csv(csv_path, company_name, fiscal_year)
    if isinstance(tool_instance, str):
        return tool_instance
    return str(tool_instance.calculate_age_ratio())


@tool
def calculate_disability_ratio_tool(
    csv_path: str,
    company_name: str = "입력사",
    fiscal_year: int = 2024,
) -> str:
    """
    CSV 파일의 직원 데이터로 장애인 고용률 및 K-ESG S-3-3 점수를 계산합니다.
    중증장애인은 is_severe_disabled=True 컬럼으로 구분하며 2명으로 환산합니다.
    (장애인고용촉진법 시행령 기준)

    Args:
        csv_path (str):
            직원 데이터 CSV 파일 경로.
            필수 컬럼: id, gender, age, employment_type, position_level
            장애인 관련 컬럼: is_disabled, is_severe_disabled (True/False)

        company_name (str, optional):
            회사명. 기본값 "입력사".

        fiscal_year (int, optional):
            회계연도. 기본값 2024.

    Returns:
        str: 장애인 고용률 및 K-ESG 점수 계산 결과 (JSON 형식 문자열)

    출력 예시:
        {
          "actual_rate":      "3.5%",
          "mandatory_rate":   "3.1%",
          "achievement":      "112.9%",
          "effective_count":  "7명",
          "kesg_achievement": 4,
          "kesg_score":       75
        }

        effective_count: 중증장애인 1명 → 2명으로 환산한 실질 인원 수
        achievement:     의무고용률 대비 달성률 (100% 이상이면 기준 충족)
    """
    tool_instance = _build_tool_input_from_csv(csv_path, company_name, fiscal_year)
    if isinstance(tool_instance, str):
        return tool_instance
    return str(tool_instance.calculate_disability_ratio())


@tool
def calculate_employment_type_ratio_tool(
    csv_path: str,
    company_name: str = "입력사",
    fiscal_year: int = 2024,
) -> str:
    """
    CSV 파일의 직원 데이터로 정규직/비정규직 비율 및 K-ESG S-2-2 점수를 계산합니다.
    고용 형태: regular(정규직), part_time(단시간), outsource(용역), dispatch(파견)

    Args:
        csv_path (str):
            직원 데이터 CSV 파일 경로.
            필수 컬럼: id, gender, age, employment_type, position_level
            employment_type 허용값: regular / part_time / outsource / dispatch

        company_name (str, optional):
            회사명. 기본값 "입력사".

        fiscal_year (int, optional):
            회계연도. 기본값 2024.

    Returns:
        str: 고용형태별 비율 및 K-ESG 점수 계산 결과 (JSON 형식 문자열)

    출력 예시:
        {
          "type_counts": {
            "regular":   72,
            "part_time":  8,
            "outsource": 12,
            "dispatch":   8
          },
          "regular_rate":      "72.0%",
          "industry_avg":      "72.6%",
          "vs_industry":       "-0.6%",
          "kesg_achievement":  3,
          "kesg_score":        50
        }

        vs_industry: 양수면 업계 평균보다 정규직 비율이 높음, 음수면 낮음
        kesg_score:  0 / 50 / 100 중 하나 (3단계 기준)
    """
    tool_instance = _build_tool_input_from_csv(csv_path, company_name, fiscal_year)
    if isinstance(tool_instance, str):
        return tool_instance
    return str(tool_instance.calculate_employment_type_ratio())