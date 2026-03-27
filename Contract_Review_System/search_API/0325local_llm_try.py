from __future__ import annotations

import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Contract_Review_System.common.local_llm_client import (
    load_env_file,
    load_runtime_config,
    resolve_runtime_env_path,
    send_chat,
)


# SerpApi 本地密钥文件路径。
# 当 `.env` 中没有配置 `SERPAPI_API_KEY` 时，会回退读取这个文件。
# 建议把它加入 `.gitignore`，避免误传到 GitHub。
SERPAPI_KEY_FILE = CURRENT_FILE.with_name("serpapi_api_key.local.txt")

# 控制最多带给模型多少条联网检索结果，先用一个比较保守的数量。
SERPAPI_RESULT_LIMIT = 5


def extract_final_answer(text: str) -> str:
    """只保留模型最终回答，去掉 thinking 内容。"""

    stripped = text.strip()
    if "</think>" in stripped:
        stripped = stripped.split("</think>")[-1].strip()
    return stripped


def extract_first_url(text: str) -> str | None:
    """从用户输入中提取第一个 URL。"""

    match = re.search(r"https?://[^\s，。；;、,)\]}>\"']+", text)
    if not match:
        return None
    return match.group(0)


def fetch_webpage_content(url: str) -> dict[str, str]:
    """直接访问指定网页并抽取标题与正文文本。

    Args:
        url: 用户明确指定的网页地址。

    Returns:
        包含标题、链接和正文摘要的字典。

    Raises:
        RuntimeError: 当网页请求失败或正文抽取失败时抛出。
    """

    current_url = url
    body = ""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/134.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())

    for _ in range(5):
        request = urllib.request.Request(
            url=current_url,
            headers=headers,
            method="GET",
        )

        try:
            with opener.open(request, timeout=60) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                body = response.read().decode(charset, errors="ignore")
                current_url = response.geturl()
                break
        except urllib.error.HTTPError as exc:
            if exc.code in {301, 302, 303, 307, 308}:
                redirect_url = exc.headers.get("Location", "").strip()
                if redirect_url:
                    current_url = urllib.parse.urljoin(current_url, redirect_url)
                    continue
            detail = exc.read().decode("utf-8", errors="ignore")
            location = exc.headers.get("Location", "").strip()
            if location:
                msg = f"网页访问失败: HTTP {exc.code}，跳转到 {location}"
            else:
                msg = f"网页访问失败: HTTP {exc.code} {detail[:200]}"
            raise RuntimeError(msg) from exc
        except urllib.error.URLError as exc:
            msg = f"网页连接失败: {exc.reason}"
            raise RuntimeError(msg) from exc
    else:
        msg = "网页重定向次数过多，已停止访问。"
        raise RuntimeError(msg)

    title_match = re.search(
        r"<title[^>]*>(.*?)</title>",
        body,
        flags=re.IGNORECASE | re.DOTALL,
    )
    raw_title = title_match.group(1).strip() if title_match else "未识别标题"

    # 先移除不适合给模型的脚本、样式和注释，再做纯文本抽取。
    cleaned_html = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        body,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned_html = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        cleaned_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned_html = re.sub(r"<!--.*?-->", " ", cleaned_html, flags=re.DOTALL)
    text_content = re.sub(r"<[^>]+>", " ", cleaned_html)
    text_content = html.unescape(text_content)
    text_content = re.sub(r"\s+", " ", text_content).strip()

    if not text_content:
        msg = "网页已成功访问，但未抽取到可用正文。"
        raise RuntimeError(msg)

    # 控制注入给模型的正文长度，避免一次塞入过多网页噪声。
    truncated_text = text_content[:4000]

    return {
        "title": raw_title,
        "link": current_url,
        "snippet": truncated_text,
    }


def _send_serpapi_request(params: dict[str, str]) -> dict[str, object]:
    """发送单次 SerpApi 请求，并返回解析后的 JSON。"""

    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url=url,
        headers={"User-Agent": "Mozilla/5.0"},
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        msg = f"SerpApi 请求失败: HTTP {exc.code} {detail}"
        raise RuntimeError(msg) from exc
    except urllib.error.URLError as exc:
        msg = f"SerpApi 连接失败: {exc.reason}"
        raise RuntimeError(msg) from exc

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        msg = f"SerpApi 返回内容不是合法 JSON: {body[:300]}"
        raise RuntimeError(msg) from exc

    if not isinstance(parsed, dict):
        msg = "SerpApi 返回的顶层内容不是字典结构。"
        raise RuntimeError(msg)
    return parsed


def _normalize_serpapi_results(
    parsed: dict[str, object],
    *,
    result_limit: int,
) -> list[dict[str, str]]:
    """把 SerpApi 返回结构统一整理成标题、链接、摘要列表。"""

    organic_results = parsed.get("organic_results")
    if not isinstance(organic_results, list):
        return []

    normalized_results: list[dict[str, str]] = []
    for item in organic_results[:result_limit]:
        if not isinstance(item, dict):
            continue

        title = str(item.get("title", "")).strip()
        link = str(item.get("link", "")).strip()
        snippet = str(item.get("snippet", "")).strip()
        if not any([title, link, snippet]):
            continue

        normalized_results.append(
            {
                "title": title or "无标题",
                "link": link or "无链接",
                "snippet": snippet or "无摘要",
            }
        )

    return normalized_results


def load_serpapi_api_key() -> str:
    """读取 SerpApi key。

    读取优先级如下：
    1. `Contract_Review_System/.env` 中的 `SERPAPI_API_KEY`
    2. 当前脚本目录下的 `serpapi_api_key.local.txt`

    Returns:
        可用的 SerpApi key。

    Raises:
        RuntimeError: 当没有找到可用 key 时抛出。
    """

    env_path = resolve_runtime_env_path()
    env_values = load_env_file(env_path)
    api_key = env_values.get("SERPAPI_API_KEY", "").strip()
    if api_key:
        return api_key

    if SERPAPI_KEY_FILE.exists():
        file_key = SERPAPI_KEY_FILE.read_text(encoding="utf-8").strip()
        if file_key:
            return file_key

    msg = (
        "未找到 SerpApi key。请二选一完成配置：\n"
        "1. 在 `Contract_Review_System/.env` 中新增 `SERPAPI_API_KEY=你的key`\n"
        f"2. 在 `{SERPAPI_KEY_FILE.name}` 文件中只写一行你的 key"
    )
    raise RuntimeError(msg)


def search_web_by_serpapi(
    query: str,
    *,
    api_key: str,
    result_limit: int = SERPAPI_RESULT_LIMIT,
) -> list[dict[str, str]]:
    """通过 SerpApi 拉取百度搜索结果。

    Args:
        query: 用户的搜索问题。
        api_key: SerpApi 的 API Key。
        result_limit: 最多返回多少条自然搜索结果。

    Returns:
        统一整理后的搜索结果列表，每条包含标题、链接和摘要。

    Raises:
        RuntimeError: 当联网请求失败或接口返回异常时抛出。
    """

    if not api_key:
        msg = "SerpApi key 为空，请先在 `.env` 或本地 key 文件中完成配置。"
        raise RuntimeError(msg)

    # 按照 SerpApi 的百度文档，这里使用：
    # - `engine=baidu` 指定百度搜索
    # - `q` 作为查询词
    # - `ct=2` 优先限制为简体中文结果
    # - `rn` 控制返回条数
    # - `pn=0` 从第一页开始
    params = {
        "engine": "baidu",
        "q": query,
        "api_key": api_key,
        "ct": "2",
        "rn": str(result_limit),
        "pn": "0",
    }

    parsed = _send_serpapi_request(params)
    error_message = str(parsed.get("error", "")).strip()
    if error_message:
        lowered_error = error_message.lower()
        if "hasn't returned any results" in lowered_error or "no results" in lowered_error:
            print(f"联网搜索提示：{error_message}")
            return []
        msg = f"SerpApi 返回错误: {error_message}"
        raise RuntimeError(msg)

    return _normalize_serpapi_results(
        parsed,
        result_limit=result_limit,
    )


def format_search_context(results: list[dict[str, str]]) -> str:
    """把 SerpApi 搜索结果整理成适合喂给模型的上下文文本。"""

    if not results:
        return "未检索到可用的联网结果。"

    lines = ["以下是联网检索结果，请优先基于这些信息回答："]
    for index, item in enumerate(results, start=1):
        lines.append(f"{index}. 标题：{item['title']}")
        lines.append(f"   链接：{item['link']}")
        lines.append(f"   摘要：{item['snippet']}")
    return "\n".join(lines)


def format_direct_page_context(page_content: dict[str, str]) -> str:
    """把直接访问到的官方网页整理成模型上下文。"""

    return (
        "以下是按用户指定地址直接访问到的网页内容，请优先基于该网页作答：\n"
        f"标题：{page_content['title']}\n"
        f"链接：{page_content['link']}\n"
        f"正文摘录：{page_content['snippet']}\n"
    )


def build_messages_with_web_context(
    conversation_history: list[tuple[str, str]],
    user_query: str,
    search_context: str,
) -> list[tuple[str, str]]:
    """把联网结果作为额外上下文注入到当前轮提问中。"""

    messages = conversation_history[:-1]
    enriched_user_query = (
        f"用户原始问题：\n{user_query}\n\n"
        f"{search_context}\n\n"
        "请你结合以上联网结果进行回答。"
        "如果联网结果不足以支持结论，要明确说明不确定点。"
        "不要输出思维链，只输出最终答案。"
    )
    messages.append(("user", enriched_user_query))
    return messages


def print_search_results(results: list[dict[str, str]]) -> None:
    """在终端先把联网命中的结果打印出来，方便人工确认。"""

    if not results:
        print("联网搜索：没有拿到可用结果。\n")
        return

    print("联网搜索结果：")
    for index, item in enumerate(results, start=1):
        print(f"{index}. {item['title']}")
        print(f"   链接：{item['link']}")
        print(f"   摘要：{item['snippet']}")
    print()


def print_direct_page_result(page_content: dict[str, str]) -> None:
    """打印直接访问网页后的命中信息。"""

    print("已直接访问指定网页：")
    print(f"标题：{page_content['title']}")
    print(f"链接：{page_content['link']}")
    print(f"正文摘录：{page_content['snippet'][:300]}...")
    print()


def main() -> None:
    """终端交互模式：每轮先联网搜索，再交给本地模型总结回答。"""

    runtime = load_runtime_config()

    system_prompt = (
        "你是一个简洁、准确的中文助手。"
        "如果用户明确给出了网址，优先直接访问该网址内容。"
        "如果用户没有给出网址，再参考联网检索结果。"
        "如果信息不充分，请明确说明。"
        "不要输出思考过程，只输出最终答案。"
    )

    # 这里保留多轮对话记忆，便于后续继续追问。
    conversation_history: list[tuple[str, str]] = [("system", system_prompt)]

    print("本地模型 + SerpApi 联网模式已启动")
    print(f"model: {runtime.model_name}")
    print(f"base_url: {runtime.base_url}")
    print("输入 exit 退出，输入 clear 清空记忆\n")

    while True:
        user_query = input("你：").strip()
        if not user_query:
            print("请输入问题。\n")
            continue

        if user_query.lower() in {"exit", "quit"}:
            print("已退出。")
            break

        if user_query.lower() == "clear":
            conversation_history = [("system", system_prompt)]
            print("记忆已清空。\n")
            continue

        try:
            # 先把原始用户问题放进历史，保证多轮对话仍然保留原始提问。
            conversation_history.append(("user", user_query))

            # 如果用户明确给了 URL，就优先直接访问该网页，避免搜索误召回。
            direct_url = extract_first_url(user_query)
            if direct_url:
                page_content = fetch_webpage_content(direct_url)
                print_direct_page_result(page_content)
                search_context = format_direct_page_context(page_content)
            else:
                # 只有在需要搜索时，才去读取 SerpApi key。
                serpapi_api_key = load_serpapi_api_key()
                search_results = search_web_by_serpapi(
                    user_query,
                    api_key=serpapi_api_key,
                )
                print_search_results(search_results)
                search_context = format_search_context(search_results)

            messages = build_messages_with_web_context(
                conversation_history,
                user_query,
                search_context,
            )

            reply = send_chat(runtime, messages)
            final_reply = extract_final_answer(reply)

            print(f"模型：{final_reply}\n")

            # 把模型回复也加入历史，便于后续继续追问。
            conversation_history.append(("assistant", final_reply))

        except Exception as exc:
            print(f"调用失败：{exc}\n")
            # 如果失败，把刚刚追加的 user 消息回滚，避免污染历史。
            if conversation_history and conversation_history[-1] == ("user", user_query):
                conversation_history.pop()


if __name__ == "__main__":
    main()
