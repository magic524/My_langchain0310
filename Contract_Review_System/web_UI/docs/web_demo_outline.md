# Web Demo 大纲

## 1. 目标

在 `Contract_Review_System/web_UI` 下搭建一个独立的 Web Demo 子模块，基于现有：

- `Contract_Review_System/word2md`
- `Contract_Review_System/only_prompt_local_llm`

先完成一个可演示、可迭代的合同审查页面，用于验证后续正式交付形态。

当前 Demo 仅聚焦：

- 上传单个合同
- 支持 `doc` / `docx`
- 选择甲方/乙方倾向
- 输入用户额外提示词
- 调用 `word2md -> only_prompt_local_llm`
- 输出批注版 Word
- 输出简版审查结果展示

当前 Demo 暂不包含：

- PDF 支持
- 法条知识库辅助审查
- 公司信息补充
- 诉讼风险检索
- 完整审查意见书输出
- 复杂页面设计
- 多用户并发与权限控制


## 2. 方案定位

本阶段 `web_UI` 的定位是：

- 作为展示和交互入口
- 不承载核心审查逻辑
- 通过服务层串联现有能力模块
- 为后续正式交付预留结构

因此，核心原则是：

- UI 层只负责输入、触发、展示、下载
- 审查流程编排放在 `services/`
- 原有 `word2md` 与 `only_prompt_local_llm` 尽量保持独立


## 3. 推荐目录结构

```text
web_UI/
├─ README.md
├─ app.py
├─ docs/
│  └─ web_demo_outline.md
├─ src/web_ui/
│  ├─ pages/
│  ├─ components/
│  ├─ state.py
│  ├─ config.py
│  └─ services/
│     ├─ review_pipeline.py
│     ├─ file_store.py
│     └─ report_loader.py
└─ outputs/
```

各部分职责建议如下：

- `app.py`
  Streamlit 入口。
- `src/web_ui/config.py`
  管理路径、默认输出目录、默认开关、展示文案等。
- `src/web_ui/state.py`
  管理页面状态，例如当前任务、结果路径、错误信息。
- `src/web_ui/components/`
  放上传区、参数区、结果区等页面组件。
- `src/web_ui/pages/`
  如果后续页面增多，再拆分页面；首版可先留空。
- `src/web_ui/services/file_store.py`
  统一管理上传文件、中间文件、输出文件路径规则。
- `src/web_ui/services/review_pipeline.py`
  串联 `word2md` 与 `only_prompt_local_llm`。
- `src/web_ui/services/report_loader.py`
  从结果目录加载批注版文件、JSON、简要报告数据，用于页面展示。
- `outputs/`
  本地 Demo 的上传、中间结果、输出结果根目录。


## 4. Demo 主流程

建议首版只维护一条主流程：

1. 用户上传 `doc` / `docx`
2. 用户选择甲方/乙方倾向
3. 用户输入额外提示词
4. UI 创建本次任务目录
5. UI 调用 `word2md`
6. UI 调用 `only_prompt_local_llm`
7. UI 展示执行状态
8. UI 提供批注版 Word 下载
9. UI 展示风险点表格或简版结果摘要

建议的数据流表达为：

`UI 输入 -> web_UI/services/review_pipeline.py -> word2md -> only_prompt_local_llm -> web_UI/services/report_loader.py -> UI 输出`


## 5. 本阶段输入输出定义

### 输入

- 合同文件
  - 当前支持：`doc`、`docx`
- 甲乙方倾向
  - 例如：`甲方倾向` / `乙方倾向`
- 用户额外提示词
  - 作为补充提示词传入 `only_prompt_local_llm`

### 输出

- 批注版 Word
- 风险点表格
- 本次运行的结果目录路径

可选附加输出：

- `dataset_with_local_llm.json`
- `local_llm_predictions.json`
- `pipeline_summary.json`


## 6. 甲乙方倾向与额外提示词的处理建议

本阶段建议将：

- 甲乙方倾向
- 用户额外提示词

统一作为 `only_prompt_local_llm` 的补充提示信息，而不是直接写死在 UI 层逻辑里。

建议后续在 `only_prompt_local_llm` 中形成明确参数接口，例如：

- `party_preference`
- `user_prompt`

由 `review_pipeline.py` 负责把 UI 输入转换为模型调用参数。

这样做的好处：

- UI 不需要理解 prompt 细节
- 以后更换页面或调用方式时可以复用
- 后续接法条知识库时也更容易扩展


## 7. 与现有模块的衔接判断

当前思路是可行的：

- 先让 UI 入口接 `word2md`
- `word2md` 输出再衔接到 `only_prompt_local_llm`
- 甲乙方倾向与额外提示词作为补充提示传递给审查模块

目前 `word2md` 与 `only_prompt_local_llm` 之间还主要依赖手动测试，这并不妨碍先做 Demo。

更合理的推进方式是：

- 首先把 Web Demo 跑通
- 然后在 `review_pipeline.py` 中逐步固化这两个模块的接口
- 最后再补自动化测试与更稳定的参数传递

也就是说，当前可以先做，但应把“手动衔接”逐步收敛成“代码层显式衔接”。


## 8. 输出目录与文件管理策略

本阶段统一放在：

- `Contract_Review_System/web_UI/outputs/`

建议使用下面的目录规则：

```text
web_UI/outputs/
└─ 20260331_143000_contract_demo/
   ├─ uploads/
   ├─ word2md/
   ├─ only_prompt_local_llm/
   └─ final/
```

其中：

- `uploads/`
  保存用户上传的原始文件副本。
- `word2md/`
  保存格式转换阶段产物。
- `only_prompt_local_llm/`
  保存审查阶段产物。
- `final/`
  放最终给 UI 展示和下载的文件。

建议规则：

- 上传文件存 `uploads/`
- 中间结果分模块分别存放
- 最终对用户可见的产物归档到 `final/`
- 每次运行生成独立任务目录
- 任务目录名用 `时间戳 + 文件名简写`

这样可以同时解决：

- 上传文件存哪
- 中间结果存哪
- 输出结果存哪
- 同名文件怎么处理
- 多次运行怎么区分


## 9. 页面范围建议

首版页面尽量简单，作为输入输出窗口即可。

建议页面只包含以下区域：

- 文件上传区
- 甲乙方倾向选择区
- 用户额外提示词输入区
- 开始审查按钮
- 当前运行状态区
- 风险点结果展示区
- 批注版 Word 下载区

暂时不做：

- 复杂导航
- 多页面切换
- 图表仪表盘
- 花哨视觉设计


## 10. 配置与失败策略的边界

对于“配置从哪里来”与“失败策略”这两个问题：

- 它们不只是 UI 问题
- 但 UI 需要承接已有设计结果

因此本阶段不必在页面层重新发明一套机制，而应采用：

- UI 调用既有配置读取方式
- UI 捕获底层异常并转换为可读提示

换句话说：

- 配置逻辑继续由既有模块管理
- 失败逻辑继续依赖底层模块现有设计
- UI 负责显示“当前失败在哪一步、建议用户怎么处理”


## 11. requirements.txt 与环境管理建议

继续使用：

```powershell
conda activate langchain
```

作为开发环境没有问题。

后续将依赖凝结成 `requirements.txt` 不是特别麻烦，但建议按“Demo 实际使用依赖”来收敛，而不是一次性导出整个大环境。

建议做法：

1. 先把 Web Demo 跑通
2. 确认 `web_UI + word2md + only_prompt_local_llm` 实际依赖了哪些包
3. 再整理出最小依赖清单

注意：

- 不建议直接把整个 conda 环境无差别导出成巨大的依赖文件
- 更适合整理一个“本项目真实需要”的 `requirements.txt`


## 12. 当前阶段的非目标

为了防止 Demo 范围失控，现阶段明确以下内容不进入本轮：

- PDF 文件支持
- 联网法条知识库
- 公司信息与诉讼风险整合
- 最终正式版审查意见书
- EXE 打包
- 多任务调度
- 复杂权限与用户管理
- 高保真 UI 设计


## 13. 下一步建议

建议按以下顺序推进：

1. 先在 `web_UI` 中搭起最小目录骨架
2. 实现 `file_store.py`，先把目录规则固定下来
3. 实现 `review_pipeline.py`，先用最直接方式串联 `word2md` 与 `only_prompt_local_llm`
4. 用 Streamlit 搭一个最小输入输出页面
5. 跑通单个合同 Demo
6. 再补结果展示与下载按钮
7. 最后再考虑接口整理与文档补充


## 14. 一句话结论

当前 Web Demo 的合理边界是：

以 `doc/docx -> word2md -> only_prompt_local_llm -> 批注版 Word/风险点表格` 为唯一主链路，先做一个简单、稳定、可演示的输入输出窗口，并把目录结构、运行目录、参数传递方式先规范下来。
