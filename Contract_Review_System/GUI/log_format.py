"""GUI 日志展示格式辅助工具。"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

DEFAULT_REMARK_EXAMPLE = "示例：重点关注付款条款、违约责任、知识产权归属，以及是否存在明显偏向对方的表述。"


@dataclass(frozen=True, slots=True)
class LogStyle:
    """单条日志在界面中的展示样式元数据。"""

    color: str
    font_weight: int = 500


def classify_log_style(message: str) -> LogStyle:
    """根据日志内容返回对应的展示样式。"""

    # 统一转小写后做关键词匹配，兼容中英混合日志。
    normalized = message.lower()
    if any(keyword in normalized for keyword in ("失败", "报错", "错误", "error", "exception", "critical")):
        return LogStyle(color="#c0392b", font_weight=700)
    if any(keyword in normalized for keyword in ("警告", "warning", "提醒")):
        return LogStyle(color="#b9770e", font_weight=600)
    if any(keyword in normalized for keyword in ("完成", "成功", "已完成", "ok")):
        return LogStyle(color="#1e8449", font_weight=700)
    if any(keyword in normalized for keyword in ("gui：", "gui:", "任务开始", "输入文件", "阶段开始", "摘要", "输出目录")):
        return LogStyle(color="#55606d", font_weight=500)
    return LogStyle(color="#355c7d", font_weight=600)


def render_log_html(message: str) -> str:
    """将日志文本渲染为 `QTextEdit` 可显示的 HTML 片段。"""

    style = classify_log_style(message)
    # 做 HTML 转义，避免日志内容中的特殊字符破坏渲染结构。
    safe_message = escape(message).replace("\n", "<br>")
    return (
        "<div style="
        f"'margin:0; color:{style.color}; font-weight:{style.font_weight};"
        " line-height:1.5; white-space:normal;'>"
        f"{safe_message}</div>"
    )
