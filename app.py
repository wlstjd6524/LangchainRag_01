import os
import tempfile
from datetime import datetime
from dotenv import load_dotenv
import gradio as gr
from langchain_core.messages import HumanMessage
from agent import run

load_dotenv()


def respond(message: str, chat_history: list, file, langchain_messages: list):
    if not message.strip():
        return "", chat_history, langchain_messages

    user_message = message
    if file is not None:
        user_message = f"{message}\n파일 경로: {file.name}"

    langchain_messages = list(langchain_messages)
    langchain_messages.append(HumanMessage(content=user_message))

    try:
        response, updated_messages = run(langchain_messages)
    except Exception as e:
        response = f"⚠️ 오류가 발생했습니다: {str(e)}"
        updated_messages = langchain_messages

    chat_history = chat_history + [
        {"role": "user",      "content": message},
        {"role": "assistant", "content": response},
    ]

    return "", chat_history, updated_messages


def save_chat(chat_history: list):
    if not chat_history:
        return gr.File(visible=False)

    lines = [
        "ESG 공시 가이드 에이전트 대화 기록",
        f"저장 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
    ]
    for msg in chat_history:
        role = "사용자" if msg["role"] == "user" else "에이전트"
        content = msg["content"]
        if isinstance(content, list):
            content = " ".join(str(c) for c in content if c)
        lines.append(f"[{role}]")
        lines.append(str(content))
        lines.append("")

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        f.write("\n".join(lines))
        return gr.File(value=f.name, visible=True)


with gr.Blocks(
    title="🌱 ESG 공시 가이드 에이전트",
    css=".chatbot { height: calc(100vh - 280px) !important; }",
) as demo:
    file_state      = gr.State(value=None)
    messages_state  = gr.State(value=[])   # 요약이 반영된 langchain 메시지

    gr.Markdown("# 🌱 ESG 공시 가이드 에이전트")
    gr.Markdown("ESG 공시 관련 질문을 입력하세요. 가이드라인 검색, 보고서 초안 작성 등을 도와드립니다.")

    chatbot = gr.Chatbot(height="calc(100vh - 280px)", type="messages")

    with gr.Row():
        msg_input  = gr.Textbox(
            placeholder="질문을 입력하세요...",
            scale=4,
            show_label=False,
            submit_btn=True,
        )

    with gr.Row(equal_height=True):
        file_upload = gr.File(
            label="CSV/PDF 파일 업로드",
            file_types=[".csv", ".pdf"],
        )
        save_btn = gr.Button("💾 대화 저장", variant="secondary", scale=0, min_width=120)

    download_file = gr.File(label="저장된 파일", visible=False)

    # 메시지 전송
    msg_input.submit(
        fn=respond,
        inputs=[msg_input, chatbot, file_state, messages_state],
        outputs=[msg_input, chatbot, messages_state],
    )

    # 파일 업로드 시 state 갱신
    file_upload.change(fn=lambda f: f, inputs=[file_upload], outputs=[file_state])

    # 대화 저장
    save_btn.click(fn=save_chat, inputs=[chatbot], outputs=[download_file])


if __name__ == "__main__":
    demo.launch()
