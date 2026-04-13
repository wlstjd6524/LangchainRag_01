# K-ESG G-4-1 윤리규범 운영 자가 점검 체크 리스트

from langchain_core.tools import tool

CHECKLIST: list[dict] = [
    {
        "id": "G4_1_1",
        "category": "윤리규범 수립",
        "question": "임직원 행동강령(윤리규범)이 문서화되어 있고 주기적으로 개정되는가?",
        "weight": 20,           # 해당 항목의 배점 (합계 100점)
        "reference": "K-ESG G-4-1",
        "legal_basis": None,    # 법적 의무 여부 (None이면 권고)
    },
    {
        "id": "G4_1_2",
        "category": "교육 및 서명",
        "question": "연 1회 이상 윤리 교육을 실시하고 서약서를 징구하는가?",
        "weight": 20,
        "reference": "K-ESG G-4-1",
        "legal_basis": None,
    },
    {
        "id": "G4_1_3",
        "category": "신고·제보 채널",
        "question": "내부 공익신고 채널(익명 포함)이 운영되고 있는가?",
        "weight": 25,
        "reference": "K-ESG G-4-1 / GRI 2-26",
        "legal_basis": "공익신고자 보호법 제2조",
    },
    {
        "id": "G4_1_4",
        "category": "신고자 보호",
        "question": "신고자 비밀보호 및 보복 방지 조치가 제도화되어 있는가?",
        "weight": 20,
        "reference": "GRI 2-26",
        "legal_basis": "공익신고자 보호법 제12조~제15조",
    },
    {
        "id": "G4_1_5",
        "category": "위반 처리 및 모니터링",
        "question": "위반 사례에 대한 징계 기준과 사후 모니터링 프로세스가 존재하는가?",
        "weight": 15,
        "reference": "K-ESG G-4-1",
        "legal_basis": None,
    },
]


@tool
def score_ethics_risk(
    responses: dict[str, bool],
    company_size: str,
) -> str:
    """
    K-ESG G-4-1 기준 윤리규범 위반 리스크를 자가 점검하고 스코어링한다.
    사용자가 윤리 규범, 내부 고발, 임직원 행동강령 현황을 물어볼 때 호출한다.
    
    Args:
        responses: 체크리스트 항목별 충족 여부
                   key는 항목 ID (예: "G4_1_1"), value는 True(충족)/False(미충족).
                   예: {"G4_1_1": True, "G4_1_2": False, ...}
        company_size: 기업 규모. K-ESG 적용 기준 조정에 사용.
                    - "large": 대기업 (자산 2조 이상 / 상장사)
                    - "medium": 중견기업
                    - "small": 중소기업
    
    Returns:
        요건별 충족 현황, 종합 점수, 리스크 등급, 개선 권고 사항을 담을 마크다운 문자열
    """
    print("##### ETHICS RISK SCORING TOOL #####")

    # 항목별 점수 계산
    total_score = 0
    item_results = []

    for item in CHECKLIST:
        satisfied = responses.get(item["id"], False)
        earned = item["weight"] if satisfied else 0
        total_score += earned

        item_results.append({
            "id": item["id"],
            "category": item["category"],
            "question": item["question"],
            "satisfied": satisfied,
            "earned": earned,
            "weight": item["weight"],
            "reference": item["reference"],
            "legal_basis": item["legal_basis"],
        })

    # 리스크 등급 판정 (점수가 낮을수록 리스크 높음)
    RISK_GRADE = [
    (80, 101, "LOW",      "위험 수준 낮음 - 윤리적 리스크 관리가 양호합니다. 현 체계 유지 권고"),
    (60,  80, "MEDIUM",   "일부 요건 미비 - 단기 개선 조치 필요"),
    (40,  60, "HIGH",     "다수 요건 누락 - 신속한 개선 조치 권고 또는 제도 정비 필요"),
    ( 0,  40, "CRITICAL", "심각한 윤리 리스크 존재 - 즉각적인 개선 및 대응 필요"),
    ]
    risk_label, risk_desc = next(
        ((label, desc) for (low, high, label, desc) in RISK_GRADE if low <= total_score < high),
        ("CRITICAL", "심각한 윤리 리스크 존재 - 즉각적인 개선 및 대응 필요"),
    )

    # 항목별 충족 현황
    item_lines = []
    for r in item_results:
        status = "충족" if r["satisfied"] else "미충족"
        basis = r["legal_basis"]
        reference = r["reference"]
        earned = r["earned"]
        weight = r["weight"]
        legal_tag = f" [⚖️ 법적 의무: {basis}]" if basis else " [📌 권고]"
        item_lines.append(
            f"- {r['id']} ({r['category']}): {status} | {earned}/{weight}점"
            f" | 근거: {reference}{legal_tag}"
        )
    item_str = "\n".join(item_lines)

    # 개선 권고 사항 생성 (미충족 항목만)
    failed_items = sorted(
        [r for r in item_results if not r["satisfied"]],
        key=lambda x: x["weight"],
        reverse=True    # 우선순위 높은 항목부터 정렬
    )

    if not failed_items:
        rec_str = "모든 항목을 충족하고 있습니다. 현 체계 유지 권고드립니다."
    else:
        rec_lines = []
        for i, item in enumerate(failed_items, 1):
            basis = item["legal_basis"]
            category = item["category"]
            question = item["question"]
            reference = item["reference"]
            legal_note = f"⚖️ 법적 의무: {basis}" if basis else "📌 권고 사항"
            rec_lines.append(
                f"{i}. [{category}] {question}\n"
                f"{legal_note} | 근거: {reference}"
            )
        rec_str = "\n\n".join(rec_lines)

    # 법적 의무 미충족 항목 경고
    legal_failures = [r for r in item_results if not r["satisfied"] and r["legal_basis"]]
    legal_warning = ""
    if legal_failures:
        failed_laws = ", ".join(r["legal_basis"] for r in legal_failures)
        legal_warning = (
            f"\n\n⚠️ 법적 의무 미충족 항목이 있습니다. 행정처벌 위험이 있으므로 즉시 조치하시기 바랍니다.\n"
            f"해당 법령: {failed_laws}"
        )

    # 최종 결과 마크다운 생성
    return (
        f"### 윤리규범 운영 자가 점검 결과\n\n"
        f"**기업 규모**: {company_size}\n"
        f"**종합 점수**: {total_score} / 100점\n"
        f"**리스크 등급**: {risk_label} - {risk_desc}\n"
        f"\n"
        f"### 항목별 충족 현황\n\n"
        f"{item_str}\n"
        f"\n"
        f"### 개선 권고 사항(우선순위 순)\n"
        f"{rec_str}\n"
        f"{legal_warning}"
    )
    