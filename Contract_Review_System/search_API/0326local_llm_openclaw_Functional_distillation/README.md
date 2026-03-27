# 0326 OpenClaw Functional Distillation

这个目录用于尝试把 openclaw 的联网检索思路蒸馏到当前本地模型脚本里。

## 文件说明

- `0326local_llm_try.py`
  - 终端交互入口。
  - 保留本地模型调用与多轮记忆模式。
  - 现在会调用下方的蒸馏核心模块。

- `openclaw_distilled_core.py`
  - 蒸馏版检索核心。
  - 主要包含：
    - 问题解析
    - URL 优先直连
    - DuckDuckGo 搜索回退
    - 查询改写
    - 来源优先级排序
    - 网页抓取
    - 相关段落筛选
    - 上下文长度控制

## 当前已经尝试蒸馏的能力

- URL 优先
- direct fetch 失败后回退搜索
- 多 query rewrite
- 官方来源优先排序
- 网页正文清洗
- 关键词段落召回
- 检索轨迹输出

## 当前明确没有蒸馏的能力

- `readability`
- browser 自动化
- Firecrawl
- BM25
- embedding / 向量检索
- rerank
- 强反爬绕过

## 运行建议

```powershell
conda activate langchain
python Contract_Review_System\search_API\0326local_llm_openclaw_Functional_distillation\0326local_llm_try.py
```

## 说明

当前版本更接近 “openclaw 的功能编排蒸馏版”，不是源码级完全复刻版。
