from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import ToolNode

from state import State, _get_llm
from tools import tools
from prompts import SYSTEM_PROMPT

llm = _get_llm()
llm_with_tools = llm.bind_tools(tools)

# 노드 인스턴스 (graph.py에서 import해서 사용)
tool_node = ToolNode(tools=tools)

def agent(state: State):
    print("##### AGENT #####")
    
    current_messages = state.get("messages", [])

    # 1. 처음 시작할 때 (메시지가 없을 때) 세팅
    if not current_messages:
        system_msg = SystemMessage(SYSTEM_PROMPT)
        human_msg = HumanMessage(content=state.get("query", ""))
        input_messages = [system_msg, human_msg]
    else:
        # 이미 메시지가 있다면 (툴 결과 등을 포함해서) 그대로 사용
        input_messages = current_messages

    # 2. LLM 호출
    response = llm_with_tools.invoke(input_messages)

    # 3. 결과 리턴
    # messages는 리스트에 추가(add)되고, answer는 최신값으로 갱신(overwrite)됩니다.
    return {
        "messages": [response], 
        "answer": response.content
    }
