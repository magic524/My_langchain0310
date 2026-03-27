from __future__ import annotations

import importlib
import html
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Contract_Review_System.common.local_llm_client import (
    load_runtime_config,
    send_chat,
)


# 这个脚本模拟 openclaw 的“轻量检索编排”思路：
# 1. 用户给了明确 URL 时，优先直接访问 URL。
# 2. URL 访问失败或用户没给 URL 时，回退到 DuckDuckGo 搜索。
# 3. 搜索时会做少量查询改写，而不是只搜原句。
# 4. 抓到网页后，不直接把整页丢给模型，而是先做正文清洗和关键词段落召回。
#
# 当前明确做不到的部分：
# - 没有使用 readability，因此正文抽取仍然是启发式规则，不如浏览器阅读模式稳。
# - 没有使用 BM25、向量检索、embedding、rerank。
# - 不能稳定处理重度 JS 渲染页、登录墙、付费墙和强反爬站点。
# - DuckDuckGo HTML 页结构如果未来变化，当前正则解析可能需要调整。


MAX_SEARCH_RESULTS = 6
MAX_FETCH_RESULTS = 3
MAX_PAGE_TEXT_CHARS = 12000
MAX_CONTEXT_CHARS = 5000
MAX_REDIRECTS = 5
SEARCH_TIMEOUT_SECONDS = 30
FETCH_TIMEOUT_SECONDS = 60


@dataclass(slots=True)
class SearchResult:
    """单条搜索结果。"""

    title: str
    link: str
    snippet: str
    source_tier: int
    source_label: str
    query: str


@dataclass(slots=True)
class PageContent:
    """单个网页抓取结果。"""

    title: str
    link: str
    summary: str
    passages: list[str]
    raw_text: str


def extract_final_answer(text: str) -> str:
    """只保留模型最终回答，去掉可能混入的 `thinking` 内容。"""

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


def build_browser_headers() -> dict[str, str]:
    """构造一个尽量接近浏览器的请求头。"""

    return {
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


def http_get_text(url: str, *, timeout: int) -> tuple[str, str]:
    """以 GET 方式请求网页并返回最终 URL 与文本内容。"""

    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
    current_url = url
    headers = build_browser_headers()

    for _ in range(MAX_REDIRECTS):
        request = urllib.request.Request(
            url=current_url,
            headers=headers,
            method="GET",
        )
        try:
            with opener.open(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                body = response.read().decode(charset, errors="ignore")
                return response.geturl(), body
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

    msg = "网页重定向次数过多，已停止访问。"
    raise RuntimeError(msg)


def extract_title_from_html(body: str) -> str:
    """从 HTML 中抽取标题。"""

    title_match = re.search(
        r"<title[^>]*>(.*?)</title>",
        body,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not title_match:
        return "未识别标题"
    return clean_inline_text(title_match.group(1))


def clean_inline_text(text: str) -> str:
    """清洗单段文本。"""

    normalized = html.unescape(text)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def html_to_paragraphs(body: str) -> list[str]:
    """把 HTML 近似切分成自然段。

    这里是启发式实现，用常见块级标签插入换行，再整体清洗。
    它不能完全替代 `readability`，但比直接取整页前几千字符更有针对性。
    """

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

    # 常见块标签前后插入换行，便于后续按段落切分。
    cleaned_html = re.sub(
        r"</?(?:p|div|section|article|li|h1|h2|h3|h4|h5|h6|br|tr|td|th)[^>]*>",
        "\n",
        cleaned_html,
        flags=re.IGNORECASE,
    )
    cleaned_html = re.sub(r"<[^>]+>", " ", cleaned_html)
    cleaned_html = html.unescape(cleaned_html)

    rough_paragraphs = re.split(r"\n+", cleaned_html)
    paragraphs: list[str] = []
    seen: set[str] = set()
    for paragraph in rough_paragraphs:
        normalized = re.sub(r"\s+", " ", paragraph).strip()
        if len(normalized) < 20:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        paragraphs.append(normalized)
    return paragraphs


def extract_query_keywords(query: str) -> list[str]:
    """从用户问题中抽取关键词，用于段落相关性打分。"""

    keyword_candidates = re.findall(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", query)
    stop_words = {
        "访问",
        "告诉我",
        "请你",
        "请问",
        "一下",
        "是否",
        "什么",
        "哪些",
        "有关",
        "相关",
        "内容",
        "条款",
        "司法解释",
        "公司",
        "合同",
        "签署",
    }
    keywords: list[str] = []
    seen: set[str] = set()
    for item in keyword_candidates:
        normalized = item.strip()
        if len(normalized) < 2:
            continue
        if normalized in stop_words:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        keywords.append(normalized)
    return keywords[:12]


def score_paragraph(paragraph: str, keywords: list[str]) -> int:
    """根据关键词出现情况给段落打一个轻量分数。"""

    lowered_paragraph = paragraph.lower()
    score = 0
    for keyword in keywords:
        lowered_keyword = keyword.lower()
        hits = lowered_paragraph.count(lowered_keyword)
        if hits > 0:
            score += hits * max(len(keyword), 2)
    return score


def select_relevant_passages(
    paragraphs: list[str],
    query: str,
    *,
    max_passages: int = 6,
) -> list[str]:
    """从网页段落中选出与问题最相关的若干段。"""

    if not paragraphs:
        return []

    keywords = extract_query_keywords(query)
    scored_items: list[tuple[int, int, str]] = []
    for index, paragraph in enumerate(paragraphs):
        score = score_paragraph(paragraph, keywords)
        if index < 3:
            score += 2
        scored_items.append((score, index, paragraph))

    # 如果关键词几乎没有命中，则回退到正文前几段。
    top_score = max(item[0] for item in scored_items)
    if top_score <= 0:
        return paragraphs[: min(max_passages, len(paragraphs))]

    sorted_items = sorted(scored_items, key=lambda item: (-item[0], item[1]))
    selected = [item[2] for item in sorted_items[:max_passages]]
    return selected


def fetch_page_content(url: str, *, query: str) -> PageContent:
    """抓取网页并选出与问题相关的正文段落。"""

    final_url, body = http_get_text(url, timeout=FETCH_TIMEOUT_SECONDS)
    title = extract_title_from_html(body)
    paragraphs = html_to_paragraphs(body)
    raw_text = " ".join(paragraphs)[:MAX_PAGE_TEXT_CHARS]
    if not raw_text:
        msg = "网页已成功访问，但未抽取到可用正文。"
        raise RuntimeError(msg)

    passages = select_relevant_passages(paragraphs, query)
    summary = "\n".join(passages)
    summary = summary[:MAX_CONTEXT_CHARS]
    return PageContent(
        title=title,
        link=final_url,
        summary=summary,
        passages=passages,
        raw_text=raw_text,
    )


def normalize_duckduckgo_link(raw_link: str) -> str:
    """把 DuckDuckGo 的跳转链接还原成真实 URL。"""

    unescaped_link = html.unescape(raw_link)
    parsed = urllib.parse.urlparse(unescaped_link)
    query_params = urllib.parse.parse_qs(parsed.query)
    uddg_values = query_params.get("uddg")
    if uddg_values:
        return urllib.parse.unquote(uddg_values[0])
    return unescaped_link


def infer_source_priority(url: str) -> tuple[int, str]:
    """按域名给来源打优先级，数字越小可信度越高。"""

    hostname = urllib.parse.urlparse(url).netloc.lower()
    if any(token in hostname for token in ["court.gov.cn", ".gov.cn", "moj.gov.cn"]):
        return 1, "政府/法院官方"
    if any(token in hostname for token in ["xinhuanet.com", "people.com.cn", "gov.cn"]):
        return 2, "权威媒体/官方门户"
    if any(token in hostname for token in ["qcc.com", "tianyancha.com", "aiqicha.baidu.com"]):
        return 3, "企业信息平台"
    if any(token in hostname for token in ["wikipedia.org", "baike.baidu.com"]):
        return 4, "百科类站点"
    return 5, "其他公开网页"


def search_duckduckgo(query: str, *, max_results: int = MAX_SEARCH_RESULTS) -> list[SearchResult]:
    """通过 DuckDuckGo HTML 页执行轻量搜索。"""

    search_url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    _, body = http_get_text(search_url, timeout=SEARCH_TIMEOUT_SECONDS)

    anchor_pattern = re.compile(
        r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        flags=re.IGNORECASE | re.DOTALL,
    )
    snippet_pattern = re.compile(
        r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>|'
        r'<div[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</div>',
        flags=re.IGNORECASE | re.DOTALL,
    )

    anchor_matches = list(anchor_pattern.finditer(body))
    snippet_matches = list(snippet_pattern.finditer(body))
    results: list[SearchResult] = []
    seen_links: set[str] = set()

    for index, anchor_match in enumerate(anchor_matches[:max_results * 2]):
        raw_link = anchor_match.group(1)
        raw_title = anchor_match.group(2)
        link = normalize_duckduckgo_link(raw_link)
        title = clean_inline_text(re.sub(r"<[^>]+>", " ", raw_title))
        snippet = ""
        if index < len(snippet_matches):
            snippet_group = snippet_matches[index].group(1) or snippet_matches[index].group(2) or ""
            snippet = clean_inline_text(re.sub(r"<[^>]+>", " ", snippet_group))

        if not link or not title:
            continue
        if link in seen_links:
            continue
        seen_links.add(link)

        source_tier, source_label = infer_source_priority(link)
        results.append(
            SearchResult(
                title=title,
                link=link,
                snippet=snippet or "无摘要",
                source_tier=source_tier,
                source_label=source_label,
                query=query,
            )
        )
        if len(results) >= max_results:
            break
    return results


def detect_query_type(query: str) -> str:
    """识别问题大致类型，用于生成更合适的搜索改写。"""

    if any(token in query for token in ["民法典", "法条", "条文", "司法解释", "条例"]):
        return "law"
    if any(token in query for token in ["诉讼", "判决书", "开庭", "执行", "案由"]):
        return "litigation"
    if any(token in query for token in ["公司", "企业", "经营", "风险", "工商"]):
        return "company"
    return "general"


def rewrite_search_queries(query: str) -> list[str]:
    """对原始问题做轻量查询改写，模拟 openclaw 的多次搜索。"""

    query_type = detect_query_type(query)
    rewrites: list[str] = [query]

    if query_type == "law":
        rewrites.extend(
            [
                f"{query} site:gov.cn",
                f"{query} site:court.gov.cn",
            ]
        )
    elif query_type == "litigation":
        rewrites.extend(
            [
                f"{query} 判决书",
                f"{query} site:court.gov.cn",
                f"{query} site:gov.cn",
            ]
        )
    elif query_type == "company":
        rewrites.extend(
            [
                f"{query} 法律风险",
                f"{query} 经营状况",
                f"{query} 诉讼",
            ]
        )
    else:
        rewrites.extend(
            [
                f"{query} 官方",
                f"{query} site:gov.cn",
            ]
        )

    deduped_queries: list[str] = []
    seen: set[str] = set()
    for item in rewrites:
        normalized = item.strip()
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped_queries.append(normalized)
    return deduped_queries[:4]


def search_with_rewrites(user_query: str) -> list[SearchResult]:
    """对多组查询改写依次搜索，并按来源优先级去重聚合。"""

    aggregated_results: list[SearchResult] = []
    seen_links: set[str] = set()

    for rewritten_query in rewrite_search_queries(user_query):
        try:
            current_results = search_duckduckgo(rewritten_query)
        except Exception:
            continue

        for result in current_results:
            if result.link in seen_links:
                continue
            seen_links.add(result.link)
            aggregated_results.append(result)

    aggregated_results.sort(key=lambda item: (item.source_tier, item.title))
    return aggregated_results[:MAX_SEARCH_RESULTS]


def fetch_relevant_pages(
    search_results: list[SearchResult],
    *,
    query: str,
) -> list[PageContent]:
    """抓取若干高优先级搜索结果，并抽取与问题相关的正文。"""

    pages: list[PageContent] = []
    for result in search_results[:MAX_FETCH_RESULTS]:
        try:
            page = fetch_page_content(result.link, query=query)
        except Exception:
            continue
        pages.append(page)
    return pages


def format_page_context(page: PageContent) -> str:
    """把单个网页内容整理为模型上下文。"""

    lines = [
        f"来源标题：{page.title}",
        f"来源链接：{page.link}",
    ]
    if page.passages:
        lines.append("相关段落：")
        for index, passage in enumerate(page.passages, start=1):
            lines.append(f"{index}. {passage}")
    else:
        lines.append(f"正文摘录：{page.summary}")
    return "\n".join(lines)


def build_retrieval_context(
    *,
    user_query: str,
    direct_page: PageContent | None,
    search_results: list[SearchResult],
    fetched_pages: list[PageContent],
) -> str:
    """把直连网页、搜索结果和正文抽取结果整合成模型上下文。"""

    context_blocks: list[str] = []

    if direct_page is not None:
        context_blocks.append(
            "以下内容来自用户明确指定的网址，请优先基于这个来源回答：\n"
            + format_page_context(direct_page)
        )
    else:
        if search_results:
            search_lines = ["以下是网络搜索结果，已经按来源可信度做了基础排序："]
            for index, item in enumerate(search_results, start=1):
                search_lines.append(
                    f"{index}. [{item.source_label}] {item.title}\n"
                    f"   链接：{item.link}\n"
                    f"   摘要：{item.snippet}\n"
                    f"   命中查询：{item.query}"
                )
            context_blocks.append("\n".join(search_lines))

        if fetched_pages:
            page_blocks = ["以下是从搜索结果中进一步抓取并抽取到的相关网页内容："]
            for page in fetched_pages:
                page_blocks.append(format_page_context(page))
            context_blocks.append("\n\n".join(page_blocks))

    if not context_blocks:
        return (
            "当前没有拿到可用的联网内容。"
            "请你直接说明未获取到可靠网络信息，不要编造来源。"
        )

    return "\n\n".join(context_blocks)


def build_messages_with_web_context(
    conversation_history: list[tuple[str, str]],
    user_query: str,
    retrieval_context: str,
) -> list[tuple[str, str]]:
    """把联网检索上下文注入当前轮用户提问。"""

    messages = conversation_history[:-1]
    enriched_user_query = (
        f"用户原始问题：\n{user_query}\n\n"
        f"{retrieval_context}\n\n"
        "请你结合上述联网结果回答。"
        "如果信息不足，请明确说明不确定点。"
        "如果引用了来源，请优先引用政府/法院/官方网站。"
        "不要输出思维链，只输出最终答案。"
    )
    messages.append(("user", enriched_user_query))
    return messages


def print_search_results(results: list[SearchResult]) -> None:
    """在终端打印搜索结果摘要。"""

    if not results:
        print("联网搜索：没有拿到可用结果。\n")
        return

    print("联网搜索结果：")
    for index, item in enumerate(results, start=1):
        print(f"{index}. [{item.source_label}] {item.title}")
        print(f"   链接：{item.link}")
        print(f"   摘要：{item.snippet}")
        print(f"   命中查询：{item.query}")
    print()


def print_direct_page_result(page: PageContent) -> None:
    """在终端打印直接访问网页后的信息。"""

    print("已直接访问指定网页：")
    print(f"标题：{page.title}")
    print(f"链接：{page.link}")
    preview = page.summary[:300] if page.summary else page.raw_text[:300]
    print(f"正文摘录：{preview}...")
    print()


def print_fetched_page_result(pages: list[PageContent]) -> None:
    """打印从搜索结果中进一步抓取到的网页内容。"""

    if not pages:
        print("网页抓取：没有成功拿到进一步的正文内容。\n")
        return

    print("进一步抓取的网页内容：")
    for index, page in enumerate(pages, start=1):
        preview = page.summary[:180] if page.summary else page.raw_text[:180]
        print(f"{index}. {page.title}")
        print(f"   链接：{page.link}")
        print(f"   摘录：{preview}...")
    print()


def main() -> None:
    """终端交互模式：保留记忆，并尝试模拟 openclaw 的检索编排。"""

    runtime = load_runtime_config()
    system_prompt = (
        "你是一个简洁、准确的中文助手。"
        "如果用户给出明确网址，优先基于该网址回答。"
        "如果没有明确网址，则先参考联网搜索结果与网页正文抽取结果。"
        "如果来源不可靠或信息不足，要明确说明。"
        "不要输出思考过程，只输出最终答案。"
    )
    conversation_history: list[tuple[str, str]] = [("system", system_prompt)]

    print("0326 本地模型 + 轻量联网检索模式已启动")
    print(f"model: {runtime.model_name}")
    print(f"base_url: {runtime.base_url}")
    print("推荐环境：conda activate langchain")
    print("说明：当前实现不依赖 SerpApi，采用 URL 直连 + DuckDuckGo 搜索回退")
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
            conversation_history.append(("user", user_query))

            direct_page: PageContent | None = None
            search_results: list[SearchResult] = []
            fetched_pages: list[PageContent] = []

            direct_url = extract_first_url(user_query)
            if direct_url:
                try:
                    direct_page = fetch_page_content(direct_url, query=user_query)
                    print_direct_page_result(direct_page)
                except Exception as direct_exc:
                    print(f"直接访问失败，将回退到搜索：{direct_exc}\n")
                    search_results = search_with_rewrites(user_query)
                    print_search_results(search_results)
                    fetched_pages = fetch_relevant_pages(search_results, query=user_query)
                    print_fetched_page_result(fetched_pages)
            else:
                search_results = search_with_rewrites(user_query)
                print_search_results(search_results)
                fetched_pages = fetch_relevant_pages(search_results, query=user_query)
                print_fetched_page_result(fetched_pages)

            retrieval_context = build_retrieval_context(
                user_query=user_query,
                direct_page=direct_page,
                search_results=search_results,
                fetched_pages=fetched_pages,
            )
            messages = build_messages_with_web_context(
                conversation_history,
                user_query,
                retrieval_context,
            )

            reply = send_chat(runtime, messages)
            final_reply = extract_final_answer(reply)

            print(f"模型：{final_reply}\n")
            conversation_history.append(("assistant", final_reply))

        except Exception as exc:
            print(f"调用失败：{exc}\n")
            if conversation_history and conversation_history[-1] == ("user", user_query):
                conversation_history.pop()


distilled = importlib.import_module(
    "Contract_Review_System.search_API."
    "0326local_llm_openclaw_Functional_distillation."
    "openclaw_distilled_core"
)


def build_messages_with_distilled_context(
    conversation_history: list[tuple[str, str]],
    user_query: str,
    retrieval_context: str,
) -> list[tuple[str, str]]:
    """把蒸馏检索上下文注入当前轮问题。"""

    messages = conversation_history[:-1]
    enriched_user_query = (
        f"用户原始问题：\n{user_query}\n\n"
        f"{retrieval_context}\n\n"
        "请你结合上述联网结果回答。"
        "如果信息不足，请明确说明不确定点。"
        "如果引用来源，请优先引用政府、法院、司法部或其他官方网站。"
        "不要输出思维链，只输出最终答案。"
    )
    messages.append(("user", enriched_user_query))
    return messages


def print_distilled_trace(trace: list[str]) -> None:
    """打印蒸馏检索轨迹。"""

    if not trace:
        return
    print("检索轨迹：")
    for item in trace:
        print(f"- {item}")
    print()


def main() -> None:
    """终端交互模式：使用独立蒸馏核心模拟 openclaw 的检索编排。"""

    runtime = load_runtime_config()
    retrieval_config = distilled.RetrievalConfig()
    system_prompt = (
        "你是一个简洁、准确的中文助手。"
        "如用户给出明确 URL，优先基于该网址正文回答；失败时再回退到搜索。"
        "回答时优先采信政府、法院、司法部等官方来源。"
        "如果来源不可靠或信息不足，要明确说明。"
        "不要输出思考过程，只输出最终答案。"
    )
    conversation_history: list[tuple[str, str]] = [("system", system_prompt)]

    print("0326 openclaw Functional distillation 已启动")
    print(f"model: {runtime.model_name}")
    print(f"base_url: {runtime.base_url}")
    print("推荐环境：conda activate langchain")
    print("说明：当前实现不依赖 SerpApi，采用 URL 优先 + DuckDuckGo 搜索回退")
    print("当前未接入：readability、browser 自动化、BM25、embedding、rerank")
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
            conversation_history.append(("user", user_query))
            query, context, direct_page, ranked_results, fetched_pages = (
                distilled.run_retrieval_pipeline(user_query, retrieval_config)
            )

            print_distilled_trace(context.trace)

            if direct_page is not None and direct_page.status == distilled.FetchStatus.SUCCESS:
                print("Direct fetch 命中：")
                print(f"标题：{direct_page.title}")
                print(f"链接：{direct_page.final_url}")
                preview = direct_page.extracted_text[:300]
                print(f"摘录：{preview}...\n")

            if ranked_results:
                print("搜索候选：")
                for index, result in enumerate(ranked_results, start=1):
                    print(f"{index}. [{result.source_label}] {result.title}")
                    print(f"   链接：{result.url}")
                    print(f"   摘要：{result.snippet}")
                    print(f"   命中查询：{result.query}")
                print()

            if fetched_pages:
                print("进一步抓取的网页：")
                for index, page in enumerate(fetched_pages, start=1):
                    preview = page.extracted_text[:180]
                    print(f"{index}. {page.title}")
                    print(f"   链接：{page.final_url}")
                    print(f"   摘录：{preview}...")
                print()

            retrieval_context = distilled.format_context_for_model(context, query, direct_page)
            messages = build_messages_with_distilled_context(
                conversation_history,
                user_query,
                retrieval_context,
            )

            reply = send_chat(runtime, messages)
            final_reply = distilled.extract_final_answer(reply)

            print(f"模型：{final_reply}\n")
            conversation_history.append(("assistant", final_reply))

        except Exception as exc:
            print(f"调用失败：{exc}\n")
            if conversation_history and conversation_history[-1] == ("user", user_query):
                conversation_history.pop()


if __name__ == "__main__":
    main()
