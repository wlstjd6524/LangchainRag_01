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
/* 1. 배경 및 전체 레이아웃 고정 */
html, body { 
    height: 100vh !important; 
    margin: 0 !important; 
    padding: 0 !important; 
    overflow: hidden !important; 
    background-color: #f3f8f5 !important; 
}

.gradio-container { 
    max-width: 100% !important; 
    height: 100vh !important;
    padding: 20px 20px 30px 20px !important; 
    box-sizing: border-box !important;
}

footer { display: none !important; }

/* 2. 사이드바 패널 (Flex 해제하고 Block으로 강제 고정) */
#sidebar-panel { 
    background-color: #ffffff !important; 
    padding: 20px 15px !important; 
    height: calc(100vh - 50px) !important; 
    max-height: calc(100vh - 50px) !important; 
    border: 1px solid #d1d5db !important; 
    border-radius: 16px !important; 
    box-shadow: 0 4px 12px rgba(0,0,0,0.03) !important; 
    
    /* 세로 스크롤만 켜고, 튀어나가는 건 무조건 숨김 */
    overflow-y: auto !important; 
    overflow-x: hidden !important; 
    
    /* 💡 Flex가 충돌의 주범이므로 block으로 강제 변경 */
    display: block !important; 
    box-sizing: border-box !important;
}

/* 3. 💡 [핵심] 사이드바 내부의 '모든(*)' 요소에 족쇄 채우기 */
#sidebar-panel * {
    max-width: 100% !important;
    box-sizing: border-box !important;
    /* 긴 한글/영문 가리지 않고 박스 끝에 닿으면 무조건 줄바꿈 */
    white-space: pre-wrap !important; 
    word-break: break-word !important; 
    overflow-wrap: break-word !important;
}

/* 4. 리스트(점표)가 오른쪽으로 밀려나가는 현상 원천 차단 */
#sidebar-panel ul {
    padding-left: 20px !important;
    margin-right: 0 !important;
    width: 100% !important;
}

#sidebar-panel h2 {
    margin-top: 0 !important;
    white-space: normal !important;
}

/* 5. 스크롤바 & 챗봇 패널 디자인 */
#sidebar-panel::-webkit-scrollbar { width: 6px; }
#sidebar-panel::-webkit-scrollbar-thumb { background: #c8e6c9; border-radius: 10px; }

/* 💡 [추가] 마크다운 내부 문단(p) 및 줄 간격 축소 */
#sidebar-panel .prose p {
    margin-top: 0.2em !important;
    margin-bottom: 0.2em !important;
    line-height: 1.4 !important;
}

/* 💡 [추가] 리스트(ul, li) 상하 여백 촘촘하게 압축 */
#sidebar-panel .prose ul {
    margin-top: 0.2em !important;
    margin-bottom: 0.8em !important; /* 각 파트(E, S, G) 사이의 여백 */
}

#sidebar-panel .prose li {
    margin-top: 0.1em !important;
    margin-bottom: 0.1em !important;
    line-height: 1.3 !important;
}

/* 💡 [추가] 소제목(h3) 위아래 여백 축소 */
#sidebar-panel .prose h3 {
    margin-top: 0.5em !important;
    margin-bottom: 0.3em !important;
}

#chat-panel {
    background-color: #ffffff !important;
    height: calc(100vh - 50px) !important; 
    padding: 20px !important; 
    border: 1px solid #d1d5db !important; 
    border-radius: 16px !important; 
    box-shadow: 0 4px 12px rgba(0,0,0,0.03) !important; 
    overflow: hidden !important; 
}

button.primary { background-color: #2e7d32 !important; color: white !important; border-radius: 10px !important; }
textarea { border-radius: 12px !important; border: 1px solid #c8e6c9 !important; background-color: #fcfdfc !important;}
"""

with gr.Blocks(title="🌱 ESG 공시 가이드 에이전트", fill_width=True, fill_height=True, css=custom_css) as demo:
    with gr.Row():
        with gr.Column(scale=3, elem_id="sidebar-panel"):
            gr.Markdown("<h2 style='color: #1b5e20; margin-top:0;'>🌱 ESG 공시 가이드<br>AI 에이전트</h2>")
            gr.Markdown("---")
            
            gr.Markdown("""
            ### ✨ 주요 기능
            
            **[Part E: 환경 (Environment)]**
            * 🏭 **탄소 배출량 산출:** Scope 1, 2, 3 배출량 자동 계산 및 데이터 분석
            * ♻️ **자원 순환 진단:** 용수 재활용률 및 폐기물 순환 지표 산출 (GRI 303/306 기준)
            * 🌿 **가이드라인 검색:** K-ESG, TCFD 등 최신 비정형 공시 가이드라인 지능형 검색 (RAG)

            **[Part S: 사회 (Social)]**
            * 👷 **산업안전 관리:** 중대재해처벌법 대응 LTIR/TRIR 지표 자동 산출 및 진단
            * 👥 **인력 다양성 KPI:** 성별·연령·고용형태별 다양성 분석 및 K-ESG 점수 환산
            * ⚖️ **노동법 가이드:** 기업 규모별 법정 의무교육 체크리스트 및 장애인 의무고용 현황 점검

            **[Part G: 지배구조 (Governance)]**
            * 📊 **이사회 벤치마킹:** OpenDART API 연동 실시간 상장사 지배구조 비교 분석
            * 🔍 **규제 동향 검색:** 최신 ESG 법령, 공시 의무 및 뉴스 실시간 웹 탐색 (Tavily)
            * 🛡️ **윤리 경영 진단:** 윤리규범 운영 상태 스코어링 및 리스크 등급/개선 권고 도출

            **[Part 통합: 지능형 분석 및 리포팅]**
            * 📉 **ESG 갭 분석:** 전 영역 데이터를 통합한 컴플라이언스 격차(Gap) 일괄 분석
            * 📝 **보고서 자동화:** 분석 결과 기반 공시 보고서 초안 생성 및 Word 파일 다운로드
            * 📁 **데이터 최적화:** 기업별 CSV 데이터 표준화 로드 및 대화 문맥 자동 요약 시스템
            """)

            gr.Markdown("---")
            gr.Markdown("**📁 첨부 가능 파일**\n* PDF 문서 (`.pdf`)\n* 데이터 파일 (`.csv`)\n\n*우측 하단 입력창의 🔗 버튼을 눌러 파일을 업로드하세요.*")

        with gr.Column(scale=7, elem_id="chat-panel"):
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
    demo.launch()
