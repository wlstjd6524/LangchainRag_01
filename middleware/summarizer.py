"""
summarizer.py
대화 요약 미들웨어

메시지 수가 임계값을 초과하면 오래된 메시지를 요약해서 토큰을 절약한다.
최근 KEEP_RECENT개의 메시지는 맥락 유지를 위해 그대로 보존한다.
"""

from langchain_core.messages import BaseMessage, SystemMessage

# 메시지 수가 이 값을 초과하면 요약 실행
SUMMARIZE_THRESHOLD = 10

# 요약 후 유지할 최근 메시지 수
KEEP_RECENT = 4


def should_summarize(messages: list[BaseMessage]) -> bool:
    return len(messages) > SUMMARIZE_THRESHOLD


def summarize_messages(messages: list[BaseMessage], llm) -> list[BaseMessage]:
    """
    오래된 메시지를 요약해서 압축된 메시지 리스트를 반환한다.

    [요약 SystemMessage] + [최근 KEEP_RECENT개 메시지]
    """
    old_messages = messages[:-KEEP_RECENT]
    recent_messages = messages[-KEEP_RECENT:]

    print(f"[Summarizer] 메시지 {len(messages)}개 → 요약 후 {1 + KEEP_RECENT}개로 압축")

    try:
        summary_response = llm.invoke([
            SystemMessage(content=(
                "다음은 사용자와 ESG 에이전트 사이의 대화 기록입니다. "
                "핵심 내용(질문 주제, 계산 결과, 검색된 정보)만 간결하게 요약하세요. "
                "불필요한 인사말이나 반복 내용은 생략하세요."
            )),
            *old_messages,
        ])
        summary_text = summary_response.content
    except Exception as e:
        print(f"[Summarizer] 요약 실패, 원본 메시지 유지: {e}")
        return messages

    summary_message = SystemMessage(content=f"[이전 대화 요약]\n{summary_text}")
    return [summary_message] + recent_messages
