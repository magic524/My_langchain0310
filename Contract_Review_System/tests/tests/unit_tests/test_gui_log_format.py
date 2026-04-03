from __future__ import annotations

from Contract_Review_System.GUI.log_format import (
    DEFAULT_REMARK_EXAMPLE,
    classify_log_style,
    render_log_html,
)


def test_classify_log_style_marks_errors_in_red() -> None:
    style = classify_log_style("任务失败：模型调用错误")

    assert style.color == "#c0392b"
    assert style.font_weight == 700


def test_classify_log_style_marks_completion_in_green() -> None:
    style = classify_log_style("GUI：任务完成。")

    assert style.color == "#1e8449"
    assert style.font_weight == 700


def test_render_log_html_escapes_html() -> None:
    rendered = render_log_html("阶段开始：<script>alert(1)</script>")

    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
    assert "<script>" not in rendered


def test_default_remark_example_is_customer_facing() -> None:
    assert "重点关注付款条款" in DEFAULT_REMARK_EXAMPLE
    assert "知识产权归属" in DEFAULT_REMARK_EXAMPLE
