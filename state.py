import os
from dotenv import load_dotenv
from typing import Optional
from typing import Annotated, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from langchain.chat_models import init_chat_model

load_dotenv()


def _get_llm():
    return init_chat_model(
        "solar-pro",
        model_provider="openai",
        openai_api_key=os.getenv("UPSTAGE_API_KEY"),
        base_url="https://api.upstage.ai/v1",
        temperature=0,
    )


class InputState(TypedDict):
    query: str


class OutputState(TypedDict):
    answer: str


class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    query: Optional[str]
    answer: Optional[str]
