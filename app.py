import os
from dotenv import load_dotenv
import gradio as gr
from langchain_core.messages import HumanMessage, AIMessage
from agent import run

load_dotenv()

def chat(message: str, history: list) -> str:
    langchain_messages = []
    
    # 1. 과거 대화 기록을 랭체인 메시지 객체로 변환하여 리스트에 차곡차곡 담습니다.
    for msg in history:
        if msg["role"] == "user":
            langchain_messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            langchain_messages.append(AIMessage(content=msg["content"]))
            
    # 2. 사용자가 방금 입력한 '현재 질문'을 리스트 맨 마지막에 추가합니다.
    langchain_messages.append(HumanMessage(content=message))

    try:
        # 3. 대화 기록과 현재 질문이 모두 담긴 리스트를 에이전트에 전달합니다.
        return run(langchain_messages)
    except Exception as e:
        return f"⚠️ 오류가 발생했습니다: {str(e)}"
def chat(message: str, history: list, file) -> str:
    if file is not None:
        message = f"{message}\n파일 경로: {file.name}"
    return run(message)


demo = gr.ChatInterface(
    fn=chat,
    title="🌱 ESG 공시 가이드 에이전트",
    description="ESG 공시 관련 질문을 입력하세요. 가이드라인 검색, 보고서 초안 작성 등을 도와드립니다.",
    additional_inputs=[
        gr.File(label="CSV 파일 업로드", file_types=[".csv"]),
    ],
    examples=[
        "전력을 500kWh 사용했을 때 탄소 배출량은?",
        "2025년 SK하이닉스 지속가능경영보고서의 핵심 내용을 요약해줘.",
        "SK텔레콤의 TCFD 보고서에서 기후 리스크 관리 방안을 찾아줘.",
        "K-ESG 가이드라인에서 환경 부문 평가 항목을 알려줘.",
        "방금 계산해 준 탄소 배출량을 줄일 수 있는 방안을 ESG 가이드라인에서 찾아줄래?",
    ],
)

if __name__ == "__main__":
    demo.launch()