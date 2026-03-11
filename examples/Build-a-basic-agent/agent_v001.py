import os
from dataclasses import dataclass

from dotenv import find_dotenv, load_dotenv
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain.chat_models import init_chat_model
from langchain.tools import ToolRuntime, tool
from langgraph.checkpoint.memory import InMemorySaver


# ===== 可尝试修改 1：系统提示词 =====
SYSTEM_PROMPT = """你是一名专业天气助手，回答风格要友好、简洁，并且偶尔使用轻松双关语。

你有两个工具：
- get_weather_for_location: 获取指定城市天气
- get_user_location: 获取当前用户位置

当用户询问天气但没有明确城市时，先用 get_user_location 获取位置再回答。"""


# ===== 可尝试修改 2：上下文结构 =====
@dataclass
class Context:
    """运行时上下文，用于向工具注入用户信息。"""

    user_id: str


# ===== 可尝试修改 3：工具函数 =====
@tool
def get_weather_for_location(city: str) -> str:
    """Get weather for a given city."""
    fake_weather_data = {
        "beijing": "多云，13°C",
        "shanghai": "小雨，16°C",
        "厦门": "晴天，-18°C",
        "florida": "晴天，29°C",
    }
    return fake_weather_data.get(city.strip().lower(), f"{city} 当前天气未知，示例数据未覆盖。")


@tool
def get_user_location(runtime: ToolRuntime[Context]) -> str:
    """Retrieve current user location from runtime context."""
    # 仅示例逻辑：你可以替换为数据库/API查询
    return "Florida" if runtime.context.user_id == "1" else "厦门"


# ===== 可尝试修改 4：结构化输出 =====
@dataclass
class ResponseFormat:
    """结构化响应格式，便于后续程序处理。"""

    punny_response: str
    weather_conditions: str | None = None


def _load_env_and_model_name() -> str:
    """Load .env and normalize model name/provider for init_chat_model."""
    load_dotenv(find_dotenv())

    model_name = os.getenv("OPENAI_LLM_MODEL") or os.getenv("MODEL_NAME") or "qwen-plus"
    openai_api_base = os.getenv("OPENAI_API_BASE")
    dashscope_api_key = os.getenv("DASHSCOPE_API_KEY")

    if dashscope_api_key and not os.getenv("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = dashscope_api_key

    if openai_api_base:
        os.environ.setdefault("OPENAI_API_BASE", openai_api_base)
        os.environ.setdefault("OPENAI_BASE_URL", openai_api_base)

    # 关键：qwen-plus 这类名字无法自动推断 provider，需要显式 openai
    if ":" not in model_name:
        return f"openai:{model_name}"
    return model_name


def main() -> None:
    """构建并运行“现实世界”版 agent（Quickstart 进阶版）。"""
    model_name = _load_env_and_model_name()
    print(f"Using model: {model_name}")

    # ===== 可尝试修改 5：模型参数 =====
    model = init_chat_model(
        model_name,
        temperature=0.5,
        timeout=20,
        max_tokens=1000,
    )

    # ===== 可尝试修改 6：记忆后端 =====
    checkpointer = InMemorySaver()

    agent = create_agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[get_user_location, get_weather_for_location],
        context_schema=Context,
        response_format=ToolStrategy(ResponseFormat),
        checkpointer=checkpointer,
    )

    # thread_id 代表同一会话，后续复用可体现 memory
    config = {"configurable": {"thread_id": "demo-thread-1"}}

    print("\n=== 第 1 轮：用户未提供地点，触发 get_user_location ===")
    response_1 = agent.invoke(
        {"messages": [{"role": "user", "content": "我在厦门，今天天气怎么样？"}]},
        config=config,
        context=Context(user_id="1"),
    )
    print(response_1["structured_response"])

    print("\n=== 第 2 轮：同一 thread_id，验证会话连续性 ===")
    response_2 = agent.invoke(
        {"messages": [{"role": "user", "content": "温度多少度。"}]},
        config=config,
        context=Context(user_id="1"),
    )
    print(response_2["structured_response"])


if __name__ == "__main__":
    main()
