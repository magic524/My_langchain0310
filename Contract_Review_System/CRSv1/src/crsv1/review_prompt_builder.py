from __future__ import annotations

from .runtime_types import ClauseReviewTask, ContractBackgroundBrief, ReviewPromptContext


BACKGROUND_SYSTEM_PROMPT = """你是合同审查系统中的背景理解助手。

你的任务不是直接列风险，而是先从合同全文中抽取后续分条审查所需的统一背景信息。

只输出 JSON，不要输出额外解释。
"""


CLAUSE_REVIEW_SYSTEM_PROMPT = """你是合同审查系统中的条款审查助手。

你会收到：
1. 合同整体背景摘要
2. 审查立场
3. 用户补充提示
4. 一个父条款及其子条款全文

请只围绕当前父条款范围输出结构化风险 JSON，不要输出多余文本。
"""


def build_background_messages(
    contract_text: str,
    prompt_context: ReviewPromptContext,
) -> list[tuple[str, str]]:
    """Build the background-brief prompt messages."""

    sections = [
        "请阅读下面这份合同全文，提炼后续多条款审查共用的背景摘要。",
        "输出格式必须是：",
        """{
  "contract_type": "合同类型",
  "transaction_purpose": "交易目标或合作背景",
  "parties_summary": "甲乙方角色和关系概述",
  "performance_path": ["关键履约步骤1", "关键履约步骤2"],
  "high_risk_topics": ["高风险主题1", "高风险主题2"],
  "review_focus": ["后续审查统一关注点1", "后续审查统一关注点2"],
  "search_hints": ["未来联网时建议搜索的关键词1", "关键词2"]
}""",
    ]
    if prompt_context.review_stance == "party_a":
        sections.append("审查立场：优先站在甲方风险控制和条款完善角度理解合同。")
    elif prompt_context.review_stance == "party_b":
        sections.append("审查立场：优先站在乙方风险控制和条款完善角度理解合同。")
    if prompt_context.extra_user_instruction:
        sections.append(f"用户补充要求：{prompt_context.extra_user_instruction}")
    sections.append(f"合同全文如下：\n{contract_text}")
    return [("system", BACKGROUND_SYSTEM_PROMPT), ("user", "\n\n".join(sections))]


def build_clause_review_messages(
    background_brief: ContractBackgroundBrief,
    task: ClauseReviewTask,
    prompt_context: ReviewPromptContext,
) -> list[tuple[str, str]]:
    """Build prompt messages for one parent clause review task."""

    sections = [
        "请审查下面这个父条款范围，并把风险尽量定位到子条款或具体句子片段。",
        "输出格式必须是：",
        """{
  "risks": [
    {
      "target_clause_id": "命中的子条款ID，没有则填父条款ID",
      "target_text": "尽量精确的原文片段",
      "risk_title": "风险标题",
      "risk_level": "high|medium|low",
      "risk_type": "付款|违约|解约|责任限制|保密|知识产权|争议解决|其他",
      "explanation": "风险说明",
      "suggestion": "修改建议",
      "evidence_source": "命中的依据，可写父条款标题或子条款标题"
    }
  ]
}""",
        f"合同类型：{background_brief.contract_type}",
        f"交易目标：{background_brief.transaction_purpose}",
        f"角色概述：{background_brief.parties_summary}",
        f"高风险主题：{'; '.join(background_brief.high_risk_topics)}",
        f"统一关注点：{'; '.join(background_brief.review_focus)}",
    ]
    if prompt_context.review_stance == "party_a":
        sections.append("审查立场：站在甲方角度优先识别风险。")
    elif prompt_context.review_stance == "party_b":
        sections.append("审查立场：站在乙方角度优先识别风险。")
    if prompt_context.extra_user_instruction:
        sections.append(f"用户补充要求：{prompt_context.extra_user_instruction}")
    sections.append(f"当前父条款任务如下：\n{task.prompt_text}")
    return [("system", CLAUSE_REVIEW_SYSTEM_PROMPT), ("user", "\n\n".join(sections))]
