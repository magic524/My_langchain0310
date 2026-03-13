import os
from dotenv import load_dotenv  # 加载.env文件
from langchain_openai import ChatOpenAI  # 如果用OpenAI
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain import create_agent  # 新API，从langchain导入

load_dotenv()  # 自动加载.env中的API密钥

# 如果用OpenAI（需要OPENAI_API_KEY）
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# 如果用本地LLM（如Ollama），替换为：
# from langchain_ollama import ChatOllama
# llm = ChatOllama(model="llama3.1", temperature=0)

# 搜索工具（需要TAVILY_API_KEY在.env中）
tools = [TavilySearchResults(max_results=3)]

# 新版create_agent（LangGraph风格）
agent = create_agent(llm, tools)

# 执行（输入格式改为messages）
result = agent.invoke({
    "messages": [{"role": "user", "content": "今天北京天气如何？"}]
})
print(result["messages"][-1].content)
