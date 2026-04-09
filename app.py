import os
from dotenv import load_dotenv
import gradio as gr
from langchain_core.messages import HumanMessage, AIMessage
from agent import run

load_dotenv()

def chat(message: str, history: list, file) -> str:
    if file is not None:
        message = f"{message}\n파일 경로: {file.name}"

    langchain_messages = []

    for msg in history:
        if msg["role"] == "user":
            langchain_messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            langchain_messages.append(AIMessage(content=msg["content"]))

    langchain_messages.append(HumanMessage(content=message))

    try:
        return run(langchain_messages)
    except Exception as e:
        return f"⚠️ 오류가 발생했습니다: {str(e)}"


demo = gr.ChatInterface(
    fn=chat,
    title="🌱 ESG 공시 가이드 에이전트",
    description="ESG 공시 관련 질문을 입력하세요. 가이드라인 검색, 보고서 초안 작성 등을 도와드립니다.",
    additional_inputs=[
        gr.File(label="CSV 파일 업로드", file_types=[".csv"]),
    ],
    examples=[
        ["전력을 500kWh 사용했을 때 탄소 배출량은?", None],
        ["2025년 SK하이닉스 지속가능경영보고서의 핵심 내용을 요약해줘.", None],
        ["SK텔레콤의 TCFD 보고서에서 기후 리스크 관리 방안을 찾아줘.", None],
        ["K-ESG 가이드라인에서 환경 부문 평가 항목을 알려줘.", None],
        ["방금 계산해 준 탄소 배출량을 줄일 수 있는 방안을 ESG 가이드라인에서 찾아줄래?", None],
    ],
)

if __name__ == "__main__":
    demo.launch()
