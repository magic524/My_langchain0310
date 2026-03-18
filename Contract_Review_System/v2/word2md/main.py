"""word2md 命令行入口。"""

from __future__ import annotations

import argparse

from common import DEFAULT_INPUT_DIR, DEFAULT_OUTPUT_DIR, LEGACY_OUTPUT_DIR, collect_sources, make_run_id, resolve_path
from pipeline import run_batch


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""

    parser = argparse.ArgumentParser(
        description="将 `.doc/.docx` 合同转换为适合 AI 阅读的 Markdown，并生成配套 JSON 元数据。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "常用命令示例：\n"
            "  python main.py --input-dir data/合同数据-2026.3.12 --recursive\n"
            "  python main.py --input-file data/.../合同.docx --run-id my_debug_run\n"
            "  python main.py --input-dir data/合同数据-2026.3.12 --recursive "
            "--output-dir Contract_Review_System/v2/word2md/outputs_md\n"
        ),
    )
    parser.add_argument("--input-file", default=None, help="单个 `.doc/.docx` 文件路径。")
    parser.add_argument(
        "--input-dir",
        default=str(DEFAULT_INPUT_DIR),
        help="输入目录路径。默认指向当前项目示例合同目录。",
    )
    parser.add_argument("--recursive", action="store_true", help="目录模式下递归扫描子目录。")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="输出根目录。默认写入 `Contract_Review_System/v2/word2md/outputs_md`。",
    )
    parser.add_argument(
        "--history-output-dir",
        action="append",
        default=None,
        help="历史输出根目录，可复用旧跑批中的 `_converted/*.docx` 作为兜底缓存。可重复传入。",
    )
    parser.add_argument("--run-id", default=None, help="输出批次名。默认使用当前时间戳。")
    parser.add_argument("--device", default="cpu", help="Docling 推理设备，默认 `cpu`。")
    parser.add_argument(
        "--no-postprocess",
        action="store_true",
        help="关闭 Markdown 后处理。默认开启，建议保留。",
    )
    return parser


def main() -> None:
    """命令行主函数。"""

    parser = build_parser()
    args = parser.parse_args()

    if args.input_file:
        input_file = args.input_file
        input_dir = None
    else:
        input_file = None
        input_dir = args.input_dir

    run_id = args.run_id or make_run_id()
    output_root = resolve_path(args.output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    history_output_roots = [output_root]
    raw_history_roots = args.history_output_dir or [str(LEGACY_OUTPUT_DIR)]
    for raw_root in raw_history_roots:
        resolved_root = resolve_path(raw_root)
        if resolved_root not in history_output_roots:
            history_output_roots.append(resolved_root)

    items = collect_sources(input_file, input_dir, args.recursive)

    print(f"\n{'#' * 68}")
    print("word2md Contract Converter")
    print(f"Run ID      : {run_id}")
    print(f"Items       : {len(items)}")
    print(f"Output Root : {output_root}")
    print("History Dir :")
    for history_root in history_output_roots:
        print(f"  - {history_root}")
    print(f"Device      : {args.device}")
    print(f"Postprocess : {not args.no_postprocess}")
    print(f"{'#' * 68}\n")

    results, summary_path = run_batch(
        items,
        run_id,
        output_root,
        args.device,
        args.no_postprocess,
        history_output_roots,
    )
    ok_count = sum(1 for result in results if result["status"] == "ok")
    fail_count = len(results) - ok_count

    print(f"\n{'=' * 68}")
    print("All done")
    print(f"Success : {ok_count}")
    print(f"Failed  : {fail_count}")
    print(f"Summary : {summary_path}")
    print(f"{'=' * 68}\n")


if __name__ == "__main__":
    main()
