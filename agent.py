from graph import create_graph

agent = create_graph()


def run(user_message: str) -> str:
    result = agent.invoke({"query": user_message})
    return result["answer"]
