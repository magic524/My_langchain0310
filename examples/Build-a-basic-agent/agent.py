import os
from dotenv import load_dotenv, find_dotenv
from langchain.agents import create_agent


def get_weather(city: str) -> str:
    """简单的工具函数：返回天气信息字符串。"""
    return f"It's always sunny in {city}!"


def main() -> None:
    """创建并运行一个非常基础的 agent，模型来源于环境变量（`.env`）。

    支持的环境变量示例（优先级按存在顺序）：
    - `OPENAI_LLM_MODEL`：通用模型名（例如 qwen-plus、gpt-4o 等），与 `OPENAI_API_BASE` 配合使用
    - `ANTHROPIC_API_KEY`：若使用Anthropic/Claude则可设置该变量
    - `DASHSCOPE_API_KEY`：示例中用户的自定义服务密钥
    - `OPENAI_API_BASE`：如果使用 OpenAI 兼容的自定义 endpoint

    运行前请在项目根目录或运行目录放置 `.env`，示例内容见 README/Notion 指南。
    """
    # 加载 .env（会查找最近的 .env 文件）
    load_dotenv(find_dotenv())

    # 读取常用环境变量
    model_name = os.getenv("OPENAI_LLM_MODEL")
    openai_api_base = os.getenv("OPENAI_API_BASE")
    dashscope_api_key = os.getenv("DASHSCOPE_API_KEY")

    # DashScope 的 OpenAI 兼容模式通常需要 OPENAI_API_KEY。
    if dashscope_api_key and not os.getenv("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = dashscope_api_key

    # 如果设置了 OPENAI_API_BASE，确保环境变量被传递到运行时
    if openai_api_base:
        os.environ.setdefault("OPENAI_API_BASE", openai_api_base)
        # 部分客户端读取 OPENAI_BASE_URL，双写可减少兼容性问题。
        os.environ.setdefault("OPENAI_BASE_URL", openai_api_base)

    # ===== 可尝试修改 1：默认模型 =====
    # 最终模型名称回退到一个安全默认（仅示例，不代表必须可用）
    # 练习建议：把 qwen-plus 改成你想尝试的模型名。
    if not model_name:
        model_name = "qwen-plus"

    # 当模型名不带 provider 前缀（如 qwen-plus）时，默认走 openai provider。
    if ":" not in model_name:
        model_name = f"openai:{model_name}"

    print(f"Using model: {model_name}")

    # ===== 可尝试修改 2：System Prompt（你当前最关心的部分） =====
    # 练习建议：在这里调整角色设定、语气、输出格式要求。
    system_prompt = "你叫林泽彬，现在因为骚扰女生被挂抖音了，现在面对公众的质疑和批评予以狡辩。"

    # create_agent 接受 model 名称或已初始化的模型对象。
    agent = create_agent(
        model=model_name,
        tools=[get_weather],
        system_prompt=system_prompt,
    )

    # ===== 可尝试修改 3：测试问题 =====
    # 练习建议：把这里改成不同任务（翻译、总结、工具调用）观察 agent 行为。
    response = agent.invoke(
        {"messages": [{"role": "user", "content": "为什么骚扰女生？"}]}
    )

    # 打印原始返回（通常包含模型输出与结构化数据）
    print("Agent response:\n", response)


if __name__ == "__main__":
    main()
