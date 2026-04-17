import time

from dotenv import load_dotenv
from langsmith import Client
from langsmith.evaluation import evaluate
from agent import run  # 에이전트 실행 함수 임포트
from langchain_upstage import ChatUpstage

from langchain_core.messages import HumanMessage

load_dotenv()
client = Client()

# 1. 에이전트 실행 함수 매핑
def predict_esg_agent(inputs: dict) -> dict:
    # LangSmith 가 에이전트를 호출할 때 사용하는 래퍼 함수
    question = inputs["question"]
    print(f"에이전트 답변 생성 중 : {question[:30]}...")

    # agent.py 의 run 함수 호출
    answer = run([HumanMessage(content=question)])
    return {"answer": answer}

# 2. 평가자 설정 : QA 정확도 평가
# LangChain 의 기본 제공 평가자로, 생성된 답변이 reference(정답지)와 의미적으로 일치하는지
eval_llm = ChatUpstage(model="solar-pro", temperature=0)

def custom_qa_evaluator(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    # 에이전트의 답변을 정답지와 비교해서 채점하는 커스텀 평가 함수
    print(" LLM 이 채점 중...")

    # 평가관에게 부여할 채점 기준 프롬프트
    prompt = f"""당신은 ESG 컨설팅 전문가이자 엄격한 채점관입니다.
사용자의 질문에 대한 AI 에이전트의 답변이 정답(Reference)과 일치하는지 평가하세요.

[사용자 질문]: {inputs['question']}
[정답(Reference)]: {reference_outputs['reference']}
[에이전트 답변]: {outputs['answer']}

평가 기준:
1. 에이전트 답변이 정답의 핵심 수치(계산 결과)와 논리(Scope 분류 등)를 모두 포함하고 있는가?
2. 숫자 연산에 할루시네이션(거짓말)이 없는가?

위 기준을 바탕으로 평가하고, 마지막 줄에 반드시 '최종 점수: 1' (통과) 또는 '최종 점수: 0' (실패) 을 적어주세요.
"""
    # LLM 에게 채점 요청
    judge_response = eval_llm.invoke(prompt).content

    # 결과에서 점수 파싱 (1점 또는 0점)
    score = 1 if "최종 점수: 1" in judge_response else 0

    print("API 한도 방지를 위한 10초 대기")
    time.sleep(20)

    question = inputs["question"]
    print(f"에이전트 답변 생성 중 : {question[:30]}...")

    answer = run([HumanMessage(content=question)])
    # LangSmith 대시보드로 보낸 결과 포맷
    return {
        "key": "qa_correctness",        # 대시보드에 표시될 평가 항목이름
        "score": score,                 # 0 또는 1
        "comment": judge_response       # 채점 이유 (대시보드에서 열람 가능)
    }

if __name__ == "__main__":
    print("ESG 에이전트 자동 평가 파이프라인 시작")

    # 3. 평가 실행
    experiment_results = evaluate(
        predict_esg_agent,
        data="ESG_Master_Pipeline_Evaluation",
        evaluators=[custom_qa_evaluator],
        experiment_prefix="ESG-Agent-Eval",
        metadata={"verson": "1.1", "description": "Custom LLM Judge Test"}
    )

    print("\n 평가완료 LangSmith 웹 대시보드에서 결과를 확인하세요.")