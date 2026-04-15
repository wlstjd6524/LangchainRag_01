import os
import time
import tempfile
from datetime import datetime
from dotenv import load_dotenv
import gradio as gr
from langchain_core.messages import HumanMessage, AIMessage

from agent import master_agent, llm, log_request, log_response, LoggingCallbackHandler
from middleware.summarizer import should_summarize, summarize_messages

load_dotenv()

def chat(message: dict, history: list):
    gr.Info("🚦 에이전트 라우터: 질문 의도를 분석하고 최적의 도구를 찾아 답변을 생성 중 입니다...")

    # 딕셔너리에서 텍스트와 파일 리스트를 분리해서 꺼냅니다.
    user_text = message.get("text", "")
    files = message.get("files", [])

    # 첨부 파일이 있을 경우 파일명을 추출하여 프롬프트 텍스트에 덧붙여줍니다.
    if files:
        file_names = []
        for f in files:
            # Gradio 버전에 따라 파일 객체 구조가 다를 수 있어 안전하게 경로 추출
            path = f if isinstance(f, str) else f.path
            file_names.append(os.path.basename(path))
        user_text += f"\n[첨부 파일]: {', '.join(file_names)}"

    langchain_messages = []

    for msg in history:
        role = msg.get("role", "")
        content = msg.get("content", "")

        # 멀티모달 환경에서는 사용자가 올린 이미지/파일 등이 튜플이나 리스트 형태로 history에 남습니다.
        # LLM에게는 순수 텍스트만 넘겨주기 위해, 문자열(str)이 아닌 기록은 건너뜁니다.
        if not isinstance(content, str):
            continue 

        if role == "user":
            langchain_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            langchain_messages.append(AIMessage(content=content))

    langchain_messages.append(HumanMessage(content=user_text))

    # 메시지 수가 임계값 초과 시 오래된 대화를 요약하여 토큰 절약
    if should_summarize(langchain_messages):
        langchain_messages = summarize_messages(langchain_messages, llm)

    log_request(user_text) # 터미널 로깅
    callback = LoggingCallbackHandler()
    start = time.time()

    try:
        partial_message = ""
        
        for chunk, metadata in master_agent.stream(
            {"messages": langchain_messages},
            config={"recursion_limit": 15, "callbacks": [callback]},
            stream_mode="messages"
        ):
            if chunk.content and isinstance(chunk.content, str):
                for char in chunk.content:
                    partial_message += char
                    yield partial_message
                    time.sleep(0.02)

        log_response(partial_message, time.time() - start, callback.tool_call_count)

    except Exception as e:
        yield f"⚠️ 오류가 발생했습니다: {str(e)}"


# UI 살짝 수정해보기
custom_css = """
/* 배경 및 스크롤 고정 */
html, body { 
    height: 100vh !important; 
    margin: 0 !important; 
    padding: 0 !important; 
    overflow: hidden !important; 
    background-color: #f3f8f5 !important; 
}

/* 💡 수정 포인트 1: 바닥 여백만 30px로 늘리기 (위20 우20 아래30 왼쪽20) */
.gradio-container { 
    max-width: 100% !important; 
    height: 100vh !important;
    padding: 20px 20px 30px 20px !important; 
    box-sizing: border-box !important;
}

footer { display: none !important; }

/* 💡 수정 포인트 2: 늘어난 바닥 여백만큼 패널 높이 계산식 수정 (위 20px + 아래 30px = 총 50px 빼기) */
#sidebar-panel { 
    background-color: #ffffff !important; 
    padding: 30px 25px !important; 
    height: calc(100vh - 50px) !important; 
    max-height: calc(100vh - 50px) !important; 
    border: 1px solid #d1d5db !important; 
    border-radius: 16px !important; 
    box-shadow: 0 4px 12px rgba(0,0,0,0.03) !important; 
    overflow-y: auto !important; 
    box-sizing: border-box !important;
}

#sidebar-panel::-webkit-scrollbar { width: 6px; }
#sidebar-panel::-webkit-scrollbar-thumb { background: #c8e6c9; border-radius: 10px; }

/* 💡 수정 포인트 3: 챗봇 패널도 똑같이 높이 50px 빼주기 */
#chat-panel {
    background-color: #ffffff !important;
    height: calc(100vh - 50px) !important; 
    max-height: calc(100vh - 50px) !important; 
    padding: 20px 20px 20px 20px !important; 
    border: 1px solid #d1d5db !important; 
    border-radius: 16px !important; 
    box-shadow: 0 4px 12px rgba(0,0,0,0.03) !important; 
    box-sizing: border-box !important;
    overflow: hidden !important; 
}

/* 버튼 및 입력창 스타일 */
button.primary { background-color: #2e7d32 !important; color: white !important; border-radius: 10px !important; }
textarea { border-radius: 12px !important; border: 1px solid #c8e6c9 !important; background-color: #fcfdfc !important;}
"""

with gr.Blocks(css=custom_css, title="🌱 ESG 공시 가이드 에이전트", fill_width=True, fill_height=True) as demo:
    with gr.Row():
        with gr.Column(scale=2, elem_id="sidebar-panel"):
            gr.Markdown("<h2 style='color: #1b5e20; margin-top:0;'>🌱 ESG 공시 가이드<br>AI 에이전트</h2>")
            gr.Markdown("---")
            
            gr.Markdown("""
            ### ✨ 주요 기능
            
            **[파트 A: 환경/ESG 공시]**
            * 🏭 Scope 1, 2, 3 탄소 배출량 자동 계산
            * 🏢 2025년 최신 기업 지속가능경영보고서 분석
            * 🌿 K-ESG, TCFD 가이드라인 맞춤형 검색
            
            **[파트 B: 정보보안/컴플라이언스]**
            * 🔒 ISMS-P 및 ISO27001 인증 기준 Gap 분석
            * 🚨 랜섬웨어 등 침해사고 초기 대응 가이드
            
            **[파트 C: 팀원 추가 기능 (예시)]**
            * 📊 ESG 평가 지표 시각화 대시보드
            * 📝 공시 보고서 초안 자동 생성기
            """)

            gr.Markdown("---")
            gr.Markdown("**📁 첨부 가능 파일**\n* PDF 문서 (`.pdf`)\n* 데이터 파일 (`.csv`)\n\n*우측 하단 입력창의 🔗 버튼을 눌러 파일을 업로드하세요.*")

        with gr.Column(scale=8, elem_id="chat-panel"):
            gr.ChatInterface(
                fn=chat,
                multimodal=True,
                fill_height=True,
                textbox=gr.MultimodalTextbox(
                    file_types=[".csv", ".pdf"],
                    placeholder="질문을 입력하거나, 파일을 이곳으로 드래그 하세요"
                ),
                examples=[
                    [{"text": "전력을 500kWh 사용했을 때 탄소 배출량은?", "files": []}],
                    [{"text": "우리 회사는 비밀번호 8자리, 3개월 변경 정책을 써. ISMS-P 기준으로 진단해 줘.", "files": []}],
                    [{"text": "2025년 SK하이닉스 지속가능경영보고서의 핵심 내용을 요약해줘.", "files": []}],
                    [{"text": "SK텔레콤의 TCFD 보고서에서 기후 리스크 관리 방안을 찾아줘.", "files": []}],
                    [{"text": "K-ESG 가이드라인에서 환경 부문 평가 항목을 알려줘.", "files": []}],
                    [{"text": "방금 계산해 준 탄소 배출량을 줄일 수 있는 방안을 ESG 가이드라인에서 찾아줄래?", "files": []}],
                    [{"text": "시멘트 1kg 생산 시 탄소 배출계수는 얼마야?", "files": []}],
                    [{"text": "철강 구매에 100만원을 지출했을 때 Scope3 탄소 배출량은?", "files": []}],
                ],
            )

if __name__ == "__main__":
    demo.launch(css=custom_css)
