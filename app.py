import gradio as gr
from agent import run


def chat(message: str, history: list, file) -> str:
    if file is not None:
        message = f"{message}\n파일 경로: {file.name}"
    return run(message)


demo = gr.ChatInterface(
    fn=chat,
    title="ESG 공시 가이드 에이전트",
    description="ESG 공시 관련 질문을 입력하세요. 가이드라인 검색, 보고서 초안 작성 등을 도와드립니다.",
    additional_inputs=[
        gr.File(label="CSV 파일 업로드", file_types=[".csv"]),
    ],
    examples=[
        ["전력을 500kWh 사용했을 때 탄소 배출량은?", None],
    ],
)

if __name__ == "__main__":
    demo.launch()