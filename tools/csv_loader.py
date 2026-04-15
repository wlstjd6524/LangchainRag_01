"""
csv_loader.py
ESG 에이전트용 CSV 파싱 툴

다양한 기업의 CSV 컬럼명을 ESG 표준 컬럼명(툴 파라미터명)으로 변환한 뒤
구조화된 데이터를 반환한다. 반환된 데이터를 바탕으로 에이전트가 계산 툴을 호출한다.

표준 컬럼명은 각 계산 툴의 파라미터명과 동일하게 맞춰져 있다:
  - calculate_safety     : total_hours_worked, lost_time_injuries, total_recordable_incidents
  - calculate_carbon_emission : electricity_kwh
"""

import csv
import json

from langchain_core.tools import tool

# ─────────────────────────────────────────────
# 표준 컬럼명(= 툴 파라미터명) → 가능한 CSV 컬럼 표현 목록
# 새로운 툴이 추가될 때 이 딕셔너리에 항목을 추가하면 된다.
# ─────────────────────────────────────────────
COLUMN_ALIASES: dict[str, list[str]] = {
    # ── calculate_safety ──────────────────────
    "total_hours_worked": [
        "total_hours_worked",
        "총 근로시간", "총근로시간", "총 근무시간", "총근무시간",
        "근로시간", "근무시간", "작업시간",
        "work_hours", "hours_worked", "total_hours", "man_hours", "manhours",
    ],
    "lost_time_injuries": [
        "lost_time_injuries",
        "휴업재해", "휴업재해건수", "휴업재해 건수", "휴업재해수", "휴업",
        "lost_time_injury", "LTI",
    ],
    "total_recordable_incidents": [
        "total_recordable_incidents",
        "전체재해", "전체재해건수", "전체 재해 건수", "전체 재해건수",
        "재해건수", "재해 건수", "전체사고", "사고건수",
        "total_incidents", "recordable_incidents", "TRI",
    ],
    # ── calculate_carbon_emission ─────────────
    "electricity_kwh": [
        "electricity_kwh",
        "전력사용량", "전력 사용량", "전력량", "전기사용량", "전기 사용량",
        "전력사용량(kwh)", "전력(kwh)", "전기(kwh)",
        "electricity", "kwh", "kWh",
    ],
    # ── calculate_employee_kpi ─────────────
    "gender": [
        "gender", "성별",
    ],
    "age": [
        "age", "나이", "연령",
    ],
    "employment_type": [
        "employment_type", "고용형태", "고용 형태",
    ],
    "position_level": [
        "position_level", "직급", "직책",
    ],
    "is_board_member": [
        "is_board_member", "이사회", "이사회여부",
    ],
    "is_disabled": [
        "is_disabled", "장애인여부", "장애인",
    ],
    "is_severe_disabled": [
        "is_severe_disabled", "중증장애인여부", "중증장애인",
    ],
}


def _build_reverse_map() -> dict[str, str]:
    """alias → 표준 컬럼명 역매핑 딕셔너리 생성 (소문자 비교용)"""
    reverse: dict[str, str] = {}
    for standard, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            reverse[alias.lower()] = standard
    return reverse


_REVERSE_MAP = _build_reverse_map()


def _normalize_columns(original_columns: list[str]) -> dict[str, str]:
    """
    원본 컬럼명 리스트를 받아 {원본명: 표준명} 매핑을 반환한다.
    인식되지 않는 컬럼은 매핑에서 제외한다.
    """
    mapping: dict[str, str] = {}
    for col in original_columns:
        standard = _REVERSE_MAP.get(col.strip().lower())
        if standard:
            mapping[col.strip()] = standard
    return mapping


def _read_csv(file_path: str) -> tuple[list[str], list[dict]]:
    """UTF-8 → EUC-KR 순서로 인코딩을 시도해 CSV를 읽는다."""
    for encoding in ("utf-8-sig", "utf-8", "euc-kr", "cp949"):
        try:
            with open(file_path, newline="", encoding=encoding) as f:
                reader = csv.DictReader(f)
                columns = list(reader.fieldnames or [])
                rows = [dict(row) for row in reader]
            return columns, rows
        except (UnicodeDecodeError, LookupError):
            continue
    raise ValueError("지원하지 않는 인코딩입니다. UTF-8 또는 EUC-KR로 저장된 파일을 사용하세요.")


@tool
def load_csv_data(file_path: str) -> str:
    """
    사용자가 CSV 파일 경로를 제공했을 때 호출한다.
    CSV를 읽어 ESG 표준 컬럼명으로 변환한 뒤 구조화된 데이터를 반환한다.
    반환된 데이터의 필드명을 확인하고, 사용자가 요청한 항목에 해당하는 계산 툴만 선택하여 호출하라.
    사용자가 요청하지 않은 항목은 데이터에 존재하더라도 계산하지 않는다.

    Args:
        file_path: CSV 파일의 경로 (예: /Users/user/data/safety_report.csv)

    Returns:
        표준화된 컬럼명과 행 데이터를 담은 JSON 문자열.
        recognized_columns: 인식된 {원본 컬럼명: 표준 컬럼명} 매핑
        unrecognized_columns: 인식되지 않은 원본 컬럼명 목록
        total_rows: 총 데이터 행 수
        data: 표준 컬럼명으로 변환된 행 데이터 리스트
    """
    print("##### CSV LOADER TOOL #####")
    print(f"##### file_path: {file_path} #####")

    try:
        original_columns, rows = _read_csv(file_path)
    except FileNotFoundError:
        return f"오류: 파일을 찾을 수 없습니다 → {file_path}"
    except Exception as e:
        return f"오류: CSV 읽기 실패 → {e}"

    col_mapping = _normalize_columns(original_columns)
    unrecognized = [c for c in original_columns if c.strip() not in col_mapping]

    if not col_mapping:
        return (
            "오류: 인식 가능한 ESG 컬럼이 없습니다.\n"
            f"원본 컬럼: {original_columns}\n"
            "COLUMN_ALIASES에 해당 컬럼명을 추가하거나 CSV 헤더를 확인하세요."
        )

    # bool로 처리할 표준 컬럼명 집합
    BOOL_COLUMNS = {"is_board_member", "is_disabled", "is_severe_disabled"}

    standardized_rows: list[dict] = []
    for row in rows:
        std_row: dict = {}
        for orig_col, std_col in col_mapping.items():
            val = row.get(orig_col, "").strip()
            if val:
                # Ture/1 -> True, 나머지 ->False로 변환
                if std_col in BOOL_COLUMNS:
                    std_row[std_col] = val.lower() in ("true", "1")
                else:
                    try:
                        std_row[std_col] = float(val.replace(",", ""))
                    except ValueError:
                        std_row[std_col] = val
        if std_row:
            standardized_rows.append(std_row)

    result = {
        "recognized_columns": col_mapping,
        "unrecognized_columns": unrecognized,
        "total_rows": len(standardized_rows),
        "data": standardized_rows,
    }

    return json.dumps(result, ensure_ascii=False, indent=2)
