from __future__ import annotations

import sys
from pathlib import Path


WEB_UI_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = WEB_UI_ROOT.parents[1]
SRC_ROOT = WEB_UI_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import streamlit as st

from web_ui.config import ALLOWED_SUFFIXES, PAGE_ICON, PAGE_TITLE
from web_ui.services.review_pipeline import run_word_to_md
from web_ui.state import clear_result_state, get_result_state, set_error_state, set_result_state


def _render_result_block() -> None:
    result = get_result_state()
    if result is None:
        return

    if result.error_message:
        st.error(result.error_message)
        if result.command:
            st.code(result.command, language="powershell")
        if result.stdout:
            st.caption("标准输出")
            st.code(result.stdout)
        if result.stderr:
            st.caption("错误输出")
            st.code(result.stderr)
        return

    st.success("转换完成。")
    st.write(f"当前阶段: `{result.stage}`")
    st.write(f"Run ID: `{result.run_id}`")
    st.write(f"输入文件: `{result.input_file}`")
    st.write(f"word2md 输出目录: `{result.word2md_run_root}`")

    artifact_paths = result.artifact_paths
    if artifact_paths:
        st.subheader("关键产物")
        for key, value in artifact_paths.items():
            st.write(f"{key}: `{value}`")

    if result.command:
        with st.expander("后台命令"):
            st.code(result.command, language="powershell")

    if result.stdout or result.stderr:
        with st.expander("运行日志"):
            if result.stdout:
                st.caption("标准输出")
                st.code(result.stdout)
            if result.stderr:
                st.caption("错误输出")
                st.code(result.stderr)


def main() -> None:
    st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON, layout="centered")
    st.title(PAGE_TITLE)
    st.caption("V0 仅接入 word2md，用于验证拖拽上传与后台转换流程。")

    uploaded_file = st.file_uploader(
        "拖入合同文件或点击上传",
        type=sorted(ALLOWED_SUFFIXES),
        accept_multiple_files=False,
        help="当前仅支持 .doc / .docx",
    )

    if uploaded_file is not None:
        st.write(f"已选择文件: `{uploaded_file.name}`")

    if st.button("开始转换", type="primary", disabled=uploaded_file is None):
        clear_result_state()
        if uploaded_file is None:
            set_error_state("请先上传一个 doc 或 docx 文件。")
        else:
            with st.spinner("正在调用 word2md 转换，请稍候..."):
                result = run_word_to_md(uploaded_file)
            set_result_state(result)

    _render_result_block()


if __name__ == "__main__":
    main()
