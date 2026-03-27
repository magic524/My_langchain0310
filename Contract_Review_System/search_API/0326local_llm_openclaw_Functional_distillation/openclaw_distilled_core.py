import html
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable


class SourceTier(Enum):
    """来源优先级，数字越小代表越可信。"""

    T0_GOVT_CENTRAL = 0
    T1_GOVT_LOCAL = 1
    T2_OFFICIAL_MEDIA = 2
    T3_LEGAL_PRO = 3
    T4_BIZ_PLATFORM = 4
    T5_WIKI = 5
    T6_SELF_MEDIA = 6


class FetchStatus(Enum):
    """网页抓取状态。"""

    SUCCESS = "success"
    FAILED_REDIRECT = "failed_redirect"
    FAILED_403 = "failed_403"
    FAILED_TIMEOUT = "failed_timeout"
    FAILED_EXTRACT = "failed_extract"
    FAILED_OTHER = "failed_other"


@dataclass(slots=True)
class SearchQuery:
    """用户查询解析结果。"""

    original: str
    direct_url: str | None
    query_type: str
    keywords: list[str]
    rewritten: list[str]


@dataclass(slots=True)
class SearchResult:
    """搜索结果条目。"""

    title: str
    url: str
    snippet: str
    source_tier: SourceTier
    source_label: str
    rank: int
    query: str


@dataclass(slots=True)
class FetchedPage:
    """抓取后的网页。"""

    url: str
    final_url: str
    title: str
    raw_html: str
    extracted_text: str
    status: FetchStatus
    source_tier: SourceTier
    char_count: int
    extractor: str
    error_message: str | None = None


@dataclass(slots=True)
class RelevantParagraph:
    """与问题相关的段落。"""

    text: str
    source_url: str
    source_title: str
    relevance_score: float
    position: str
    source_tier: SourceTier


@dataclass(slots=True)
class RetrievalContext:
    """最终送给模型的上下文。"""

    paragraphs: list[RelevantParagraph]
    total_chars: int
    sources: list[str]
    is_truncated: bool
    trace: list[str]


@dataclass(slots=True)
class RetrievalConfig:
    """蒸馏版检索配置。"""

    search_count: int = 8
    search_provider: str = "duckduckgo-html"
    fetch_timeout_seconds: int = 15
    search_timeout_seconds: int = 15
    max_redirects: int = 5
    max_fetch_pages: int = 4
    max_page_chars: int = 5000
    max_paragraphs_per_page: int = 6
    max_context_chars: int = 8000
    min_relevance_score: float = 0.15
    source_priority: dict[str, SourceTier] = field(
        default_factory=lambda: {
            "moj.gov.cn": SourceTier.T0_GOVT_CENTRAL,
            "court.gov.cn": SourceTier.T0_GOVT_CENTRAL,
            ".gov.cn": SourceTier.T1_GOVT_LOCAL,
            "people.com.cn": SourceTier.T2_OFFICIAL_MEDIA,
            "people.cn": SourceTier.T2_OFFICIAL_MEDIA,
            "xinhuanet.com": SourceTier.T2_OFFICIAL_MEDIA,
            "thepaper.cn": SourceTier.T2_OFFICIAL_MEDIA,
            "faxin.cn": SourceTier.T3_LEGAL_PRO,
            "pkulaw.com": SourceTier.T3_LEGAL_PRO,
            "qcc.com": SourceTier.T4_BIZ_PLATFORM,
            "tianyancha.com": SourceTier.T4_BIZ_PLATFORM,
            "aiqicha.baidu.com": SourceTier.T4_BIZ_PLATFORM,
            "baike.baidu.com": SourceTier.T5_WIKI,
            "zhihu.com": SourceTier.T5_WIKI,
        }
    )


def extract_final_answer(text: str) -> str:
    """只保留模型最终回答。"""

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


def classify_query_type(query: str) -> str:
    """识别问题类型。"""

    if any(token in query for token in ["民法典", "法条", "条文", "司法解释", "条例"]):
        return "legal"
    if any(token in query for token in ["诉讼", "判决书", "执行", "案由", "开庭"]):
        return "litigation"
    if any(token in query for token in ["公司", "企业", "经营", "风险", "工商"]):
        return "company"
    return "general"


def extract_keywords(query: str) -> list[str]:
    """提取关键词。"""

    candidates = re.findall(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", query)
    stop_words = {
        "访问",
        "请你",
        "请问",
        "告诉我",
        "一下",
        "什么",
        "哪些",
        "有关",
        "相关",
        "信息",
        "内容",
        "条款",
        "司法解释",
    }
    keywords: list[str] = []
    seen: set[str] = set()
    for item in candidates:
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


def rewrite_query(query: str, query_type: str) -> list[str]:
    """生成少量查询改写。"""

    rewrites = [query]
    if query_type == "legal":
        rewrites.extend(
            [
                f"{query} 条文",
                f"{query} 司法解释",
                f"{query} site:gov.cn",
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
                f"{query} 经营状况",
                f"{query} 法律风险",
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

    deduped: list[str] = []
    seen: set[str] = set()
    for item in rewrites:
        normalized = item.strip()
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped[:4]


def parse_query(user_query: str) -> SearchQuery:
    """解析用户问题。"""

    direct_url = extract_first_url(user_query)
    query_type = classify_query_type(user_query)
    keywords = extract_keywords(user_query)
    rewritten = rewrite_query(user_query, query_type)
    return SearchQuery(
        original=user_query,
        direct_url=direct_url,
        query_type=query_type,
        keywords=keywords,
        rewritten=rewritten,
    )


def build_browser_headers() -> dict[str, str]:
    """构造浏览器风格请求头。"""

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


def clean_inline_text(text: str) -> str:
    """清洗单行文本。"""

    normalized = html.unescape(text)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def get_source_tier(url: str, config: RetrievalConfig) -> SourceTier:
    """根据 URL 判断来源优先级。"""

    hostname = urllib.parse.urlparse(url).netloc.lower()
    for domain, tier in config.source_priority.items():
        if domain in hostname:
            return tier
    return SourceTier.T6_SELF_MEDIA


def get_source_label(tier: SourceTier) -> str:
    """来源优先级对应的中文标签。"""

    mapping = {
        SourceTier.T0_GOVT_CENTRAL: "中央政府/法院官方",
        SourceTier.T1_GOVT_LOCAL: "地方政府官方",
        SourceTier.T2_OFFICIAL_MEDIA: "权威媒体",
        SourceTier.T3_LEGAL_PRO: "专业法律平台",
        SourceTier.T4_BIZ_PLATFORM: "企业信息平台",
        SourceTier.T5_WIKI: "百科/知识平台",
        SourceTier.T6_SELF_MEDIA: "其他公开网页",
    }
    return mapping[tier]


def normalize_duckduckgo_link(raw_link: str) -> str:
    """把 DuckDuckGo 跳转链接还原为真实 URL。"""

    unescaped_link = html.unescape(raw_link)
    parsed = urllib.parse.urlparse(unescaped_link)
    params = urllib.parse.parse_qs(parsed.query)
    uddg_values = params.get("uddg")
    if uddg_values:
        return urllib.parse.unquote(uddg_values[0])
    return unescaped_link


def http_get_text(
    url: str,
    *,
    timeout: int,
    max_redirects: int,
) -> tuple[str, str]:
    """执行 GET 请求，返回最终 URL 和文本。"""

    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
    headers = build_browser_headers()
    current_url = url

    for _ in range(max_redirects):
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
                raise RuntimeError("检测到重定向，但没有拿到 Location 头。") from exc
            if exc.code == 403:
                raise PermissionError("网页返回 403，疑似被站点限制访问。") from exc
            detail = exc.read().decode("utf-8", errors="ignore")
            msg = f"网页访问失败: HTTP {exc.code} {detail[:200]}"
            raise RuntimeError(msg) from exc
        except urllib.error.URLError as exc:
            msg = f"网页连接失败: {exc.reason}"
            raise RuntimeError(msg) from exc

    msg = "网页重定向次数过多，疑似重定向循环。"
    raise RuntimeError(msg)


def extract_title_from_html(body: str) -> str:
    """从 HTML 中提取标题。"""

    title_match = re.search(
        r"<title[^>]*>(.*?)</title>",
        body,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not title_match:
        return "未识别标题"
    return clean_inline_text(title_match.group(1))


def html_to_paragraphs(body: str) -> list[str]:
    """启发式切分 HTML 为自然段。"""

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


def score_paragraph(paragraph: str, keywords: Iterable[str], position: str) -> float:
    """对段落做轻量相关性打分。"""

    lowered_paragraph = paragraph.lower()
    score = 0.0
    for keyword in keywords:
        lowered_keyword = keyword.lower()
        hits = lowered_paragraph.count(lowered_keyword)
        if hits > 0:
            score += hits * max(len(keyword), 2) / 10

    if position == "title":
        score += 0.4
    elif position == "first":
        score += 0.2
    return score


def direct_fetch(url: str, config: RetrievalConfig) -> tuple[bool, FetchedPage | None]:
    """优先尝试直接抓取用户指定 URL。"""

    tier = get_source_tier(url, config)
    try:
        final_url, body = http_get_text(
            url,
            timeout=config.fetch_timeout_seconds,
            max_redirects=config.max_redirects,
        )
    except PermissionError as exc:
        return False, FetchedPage(
            url=url,
            final_url=url,
            title="未抓取成功",
            raw_html="",
            extracted_text="",
            status=FetchStatus.FAILED_403,
            source_tier=tier,
            char_count=0,
            extractor="heuristic-html",
            error_message=str(exc),
        )
    except RuntimeError as exc:
        status = (
            FetchStatus.FAILED_REDIRECT
            if "重定向" in str(exc)
            else FetchStatus.FAILED_OTHER
        )
        return False, FetchedPage(
            url=url,
            final_url=url,
            title="未抓取成功",
            raw_html="",
            extracted_text="",
            status=status,
            source_tier=tier,
            char_count=0,
            extractor="heuristic-html",
            error_message=str(exc),
        )

    paragraphs = html_to_paragraphs(body)
    extracted_text = "\n".join(paragraphs)[: config.max_page_chars]
    if not extracted_text:
        return False, FetchedPage(
            url=url,
            final_url=final_url,
            title=extract_title_from_html(body),
            raw_html=body,
            extracted_text="",
            status=FetchStatus.FAILED_EXTRACT,
            source_tier=tier,
            char_count=0,
            extractor="heuristic-html",
            error_message="网页已访问成功，但未抽取到可用正文。",
        )

    return True, FetchedPage(
        url=url,
        final_url=final_url,
        title=extract_title_from_html(body),
        raw_html=body,
        extracted_text=extracted_text,
        status=FetchStatus.SUCCESS,
        source_tier=tier,
        char_count=len(extracted_text),
        extractor="heuristic-html",
        error_message=None,
    )


def search_duckduckgo(query: str, config: RetrievalConfig) -> list[SearchResult]:
    """通过 DuckDuckGo HTML 执行搜索。"""

    search_url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    _, body = http_get_text(
        search_url,
        timeout=config.search_timeout_seconds,
        max_redirects=config.max_redirects,
    )

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

    for index, anchor_match in enumerate(anchor_matches[: config.search_count * 2]):
        raw_link = anchor_match.group(1)
        raw_title = anchor_match.group(2)
        url = normalize_duckduckgo_link(raw_link)
        title = clean_inline_text(re.sub(r"<[^>]+>", " ", raw_title))
        snippet = ""
        if index < len(snippet_matches):
            snippet_group = snippet_matches[index].group(1) or snippet_matches[index].group(2) or ""
            snippet = clean_inline_text(re.sub(r"<[^>]+>", " ", snippet_group))

        if not url or not title:
            continue
        if url in seen_links:
            continue
        seen_links.add(url)

        source_tier = get_source_tier(url, config)
        results.append(
            SearchResult(
                title=title,
                url=url,
                snippet=snippet or "无摘要",
                source_tier=source_tier,
                source_label=get_source_label(source_tier),
                rank=len(results) + 1,
                query=query,
            )
        )
        if len(results) >= config.search_count:
            break
    return results


def fallback_search(queries: list[str], config: RetrievalConfig) -> list[SearchResult]:
    """执行多查询搜索并聚合去重。"""

    aggregated: list[SearchResult] = []
    seen_links: set[str] = set()
    for query in queries:
        try:
            current_results = search_duckduckgo(query, config)
        except Exception:
            continue

        for result in current_results:
            if result.url in seen_links:
                continue
            seen_links.add(result.url)
            aggregated.append(result)
    return aggregated


def rank_sources(results: list[SearchResult], config: RetrievalConfig) -> list[SearchResult]:
    """按来源优先级和搜索排名排序。"""

    _ = config
    return sorted(results, key=lambda item: (item.source_tier.value, item.rank))


def fetch_ranked_pages(
    ranked_results: list[SearchResult],
    config: RetrievalConfig,
) -> list[FetchedPage]:
    """抓取排序后的若干个网页。"""

    pages: list[FetchedPage] = []
    for result in ranked_results[: config.max_fetch_pages]:
        is_success, page = direct_fetch(result.url, config)
        if not page:
            continue
        if is_success and page.status == FetchStatus.SUCCESS:
            pages.append(page)
    return pages


def filter_paragraphs(
    pages: list[FetchedPage],
    query: SearchQuery,
    config: RetrievalConfig,
) -> list[RelevantParagraph]:
    """从抓取到的网页中筛选相关段落。"""

    paragraphs: list[RelevantParagraph] = []
    for page in pages:
        raw_paragraphs = page.extracted_text.splitlines()
        for index, paragraph in enumerate(raw_paragraphs):
            normalized = clean_inline_text(paragraph)
            if len(normalized) < 20:
                continue
            position = "body"
            if index == 0:
                position = "title"
            elif index < 3:
                position = "first"
            relevance_score = score_paragraph(normalized, query.keywords, position)
            if relevance_score < config.min_relevance_score:
                continue
            paragraphs.append(
                RelevantParagraph(
                    text=normalized,
                    source_url=page.final_url,
                    source_title=page.title,
                    relevance_score=relevance_score,
                    position=position,
                    source_tier=page.source_tier,
                )
            )

    paragraphs.sort(
        key=lambda item: (item.source_tier.value, -item.relevance_score, item.position)
    )
    return paragraphs[: config.max_paragraphs_per_page * config.max_fetch_pages]


def build_context(
    paragraphs: list[RelevantParagraph],
    config: RetrievalConfig,
    trace: list[str],
) -> RetrievalContext:
    """把相关段落组装成最终上下文。"""

    selected: list[RelevantParagraph] = []
    sources: list[str] = []
    total_chars = 0
    source_seen: set[str] = set()

    for paragraph in paragraphs:
        part = f"[来源：{paragraph.source_url}]\n{paragraph.text}\n"
        if total_chars + len(part) > config.max_context_chars:
            return RetrievalContext(
                paragraphs=selected,
                total_chars=total_chars,
                sources=sources,
                is_truncated=True,
                trace=trace,
            )

        selected.append(paragraph)
        total_chars += len(part)
        if paragraph.source_url not in source_seen:
            source_seen.add(paragraph.source_url)
            sources.append(paragraph.source_url)

    return RetrievalContext(
        paragraphs=selected,
        total_chars=total_chars,
        sources=sources,
        is_truncated=False,
        trace=trace,
    )


def format_context_for_model(
    context: RetrievalContext,
    query: SearchQuery,
    direct_page: FetchedPage | None,
) -> str:
    """把检索上下文格式化成送给模型的文本。"""

    lines: list[str] = []
    lines.append(f"用户原始问题：{query.original}")
    if direct_page is not None and direct_page.status == FetchStatus.SUCCESS:
        lines.append("说明：优先使用用户明确指定网址抓取到的内容。")
        lines.append(f"指定网址：{direct_page.final_url}")
        lines.append(f"网页标题：{direct_page.title}")

    if context.trace:
        lines.append("检索轨迹：")
        for item in context.trace:
            lines.append(f"- {item}")

    if context.paragraphs:
        lines.append("相关网页段落：")
        for index, paragraph in enumerate(context.paragraphs, start=1):
            lines.append(
                f"{index}. [{get_source_label(paragraph.source_tier)}] "
                f"{paragraph.source_title}\n"
                f"   链接：{paragraph.source_url}\n"
                f"   段落：{paragraph.text}"
            )
    else:
        lines.append("当前没有拿到可靠的网页正文内容。")

    lines.append(
        "限制说明：当前蒸馏版没有接入 readability、browser 自动化、"
        "BM25、embedding 或 rerank。对强反爬或 JS 渲染页面可能不稳定。"
    )
    return "\n".join(lines)


def run_retrieval_pipeline(
    user_query: str,
    config: RetrievalConfig | None = None,
) -> tuple[SearchQuery, RetrievalContext, FetchedPage | None, list[SearchResult], list[FetchedPage]]:
    """执行完整蒸馏检索流程。"""

    effective_config = config or RetrievalConfig()
    query = parse_query(user_query)
    trace: list[str] = [f"问题类型：{query.query_type}"]

    direct_page: FetchedPage | None = None
    search_results: list[SearchResult] = []
    fetched_pages: list[FetchedPage] = []

    if query.direct_url:
        trace.append(f"检测到用户显式 URL：{query.direct_url}")
        is_success, page = direct_fetch(query.direct_url, effective_config)
        if page is not None:
            direct_page = page
        if is_success and page is not None and page.status == FetchStatus.SUCCESS:
            trace.append("Direct fetch 成功，优先使用指定网页。")
            paragraphs = filter_paragraphs([page], query, effective_config)
            context = build_context(paragraphs, effective_config, trace)
            return query, context, direct_page, search_results, fetched_pages

        if page is not None and page.error_message:
            trace.append(f"Direct fetch 失败：{page.error_message}")
        else:
            trace.append("Direct fetch 失败，准备回退到搜索。")

    else:
        trace.append("未检测到显式 URL，直接进入搜索回退流程。")

    trace.append(f"查询改写：{query.rewritten}")
    search_results = fallback_search(query.rewritten, effective_config)
    ranked_results = rank_sources(search_results, effective_config)
    trace.append(f"聚合搜索结果数量：{len(search_results)}")

    fetched_pages = fetch_ranked_pages(ranked_results, effective_config)
    trace.append(f"成功抓取网页数量：{len(fetched_pages)}")

    paragraphs = filter_paragraphs(fetched_pages, query, effective_config)
    trace.append(f"筛选后的相关段落数量：{len(paragraphs)}")
    context = build_context(paragraphs, effective_config, trace)
    return query, context, direct_page, ranked_results, fetched_pages
