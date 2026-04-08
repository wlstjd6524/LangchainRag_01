from langgraph.graph import END, StateGraph, START
from langgraph.prebuilt import tools_condition

from state import State, InputState, OutputState
from nodes import agent, tool_node


def create_agent_graph():
    graph_builder = StateGraph(State, input_schema=InputState, output_schema=OutputState)

    # 노드 추가
    graph_builder.add_node("agent", agent)
    graph_builder.add_node("tools", tool_node)

    # 엣지 연결
    graph_builder.add_edge(START, "agent")

    graph_builder.add_conditional_edges(
        "agent",
        tools_condition,
        {
            "tools": "tools",
            END: END,
        },
    )

    # 도구 실행 후 다시 agent로 (ReAct 루프)
    graph_builder.add_edge("tools", "agent")

    return graph_builder.compile()


def create_graph():
    return create_agent_graph()
