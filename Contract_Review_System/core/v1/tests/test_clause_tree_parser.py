from __future__ import annotations

from Contract_Review_System.core.v1.src.crsv1.clause_tree_parser import build_review_tasks, parse_clause_tree


def test_parse_clause_tree_preface_and_chinese_top_children() -> None:
    markdown = """
甲方：甲公司
法定代表人：张三
地址：上海
乙方：乙公司
鉴于甲方委托乙方提供服务，双方达成如下协议。
一、服务范围
1、服务项目：软件升级
2、服务地点：坦桑尼亚
5、服务内容简述：
5.1 乙方应在期限内完成升级。
二、双方权利与义务
1、甲方有权监督乙方服务质量。
"""
    clause_tree = parse_clause_tree("contract_a", markdown)

    assert len(clause_tree) == 3
    assert clause_tree[0].heading == "前言与合同主体"
    assert clause_tree[1].heading.startswith("一、服务范围")
    assert len(clause_tree[1].children) == 3
    assert clause_tree[1].children[0].heading.startswith("1、服务项目")
    assert clause_tree[1].children[-1].heading.startswith("5、服务内容简述")
    assert clause_tree[1].children[-1].children[0].heading.startswith("5.1")
    assert clause_tree[2].heading.startswith("二、双方权利与义务")
    assert clause_tree[2].children[0].heading.startswith("1、甲方有权")


def test_parse_clause_tree_numeric_top_and_decimal_children() -> None:
    markdown = """
1. 总则
本合同适用于合作事项。
1.1 定义
术语定义如下。
1.2 适用范围
适用于全部项目。
2. 付款
付款安排如下。
"""
    clause_tree = parse_clause_tree("contract_b", markdown)
    assert len(clause_tree) == 2
    assert clause_tree[0].heading.startswith("1. 总则")
    assert clause_tree[0].children[0].heading.startswith("1.1 定义")
    tasks = build_review_tasks("contract_b", clause_tree)
    assert len(tasks) == 2
    assert tasks[0].child_clause_ids
