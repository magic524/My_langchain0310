from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from word2md.mammoth_converter import html_to_markdown


def test_html_to_markdown_recovers_chinese_major_headings_from_ordered_list() -> None:
    html = (
        "<p><strong>一、服务范围</strong></p>"
        "<p>1、服务项目：车播放器软件升级</p>"
        "<ol><li><strong>双方权利与义务</strong></li></ol>"
        "<p>1、甲方有权要求乙方按照本协议约定提供售后服务。</p>"
        "<p><strong>三、服务费用及付款方式</strong></p>"
        "<ol><li><strong>违约责任</strong></li></ol>"
        "<p><strong>五、争议解决</strong></p>"
    )

    markdown = html_to_markdown(html)

    assert "**一、服务范围**" in markdown
    assert "**二、双方权利与义务**" in markdown
    assert "**三、服务费用及付款方式**" in markdown
    assert "**四、违约责任**" in markdown
    assert "1. **双方权利与义务**" not in markdown
    assert "1. **违约责任**" not in markdown


def test_html_to_markdown_keeps_normal_ordered_list_items() -> None:
    html = (
        "<p><strong>四、双方责任与义务</strong></p>"
        "<p><strong>（一）甲方责任与义务</strong></p>"
        "<ol>"
        "<li>按本协议约定的时间、规格、数量向乙方交付赞助物资。</li>"
        "<li>及时向乙方提供品牌logo、广告设计规范。</li>"
        "</ol>"
    )

    markdown = html_to_markdown(html)

    assert "**四、双方责任与义务**" in markdown
    assert "**（一）甲方责任与义务**" in markdown
    assert "1. 按本协议约定的时间、规格、数量向乙方交付赞助物资。" in markdown
    assert "2. 及时向乙方提供品牌logo、广告设计规范。" in markdown


def test_html_to_markdown_preserves_explicit_arabic_major_headings() -> None:
    html = (
        "<p><strong>1. 本协议的目的</strong></p>"
        "<p>本协议的目的是设定双方同意的条款。</p>"
        "<p><strong>2. 保密信息内容</strong></p>"
        "<p>在本协议中，保密信息是指由甲方向乙方提供的资料。</p>"
    )

    markdown = html_to_markdown(html)

    assert "**1. 本协议的目的**" in markdown
    assert "**2. 保密信息内容**" in markdown
