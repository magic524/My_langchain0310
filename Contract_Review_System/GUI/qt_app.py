"""合同审查系统 GUI 第一版窗口实现。"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from .log_format import DEFAULT_REMARK_EXAMPLE, render_log_html
from .service import GuiPipelineService, GuiReviewRequest, GuiReviewResult
from .styles import APP_STYLESHEET

try:
    from PyQt6.QtCore import QObject, Qt, QThread, QUrl, pyqtSignal
    from PyQt6.QtGui import QDesktopServices, QTextCursor
    from PyQt6.QtWidgets import (
        QApplication,
        QComboBox,
        QFileDialog,
        QFrame,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QSplitter,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    msg = "缺少 PyQt6，请先在 `langchain` 环境中执行 `pip install PyQt6`。"
    raise RuntimeError(msg) from exc


class PipelineWorker(QObject):
    """在后台线程执行审查流水线，并通过信号回传进度。"""

    progress_changed = pyqtSignal(int, str)
    log_emitted = pyqtSignal(str)
    finished = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, request: GuiReviewRequest, service: GuiPipelineService) -> None:
        super().__init__()
        self.request = request
        self.service = service

    def run(self) -> None:
        """执行服务调用，并将实时状态推送回主线程 UI。"""

        try:
            result = self.service.run(
                self.request,
                progress_callback=self.progress_changed.emit,
                log_callback=self.log_emitted.emit,
            )
        except Exception as exc:  # noqa: BLE001
            # 后台线程内统一捕获并通知 UI，避免线程异常直接中断程序。
            self.failed.emit(str(exc))
            return
        self.finished.emit(asdict(result))


class ContractReviewMainWindow(QMainWindow):
    """合同审查 GUI 主窗口。"""

    def __init__(self) -> None:
        super().__init__()
        self.service = GuiPipelineService()
        self.worker_thread: QThread | None = None
        self.worker: PipelineWorker | None = None
        self.latest_result: GuiReviewResult | None = None

        self.setWindowTitle("合同审查系统 GUI 第一版")
        self.resize(1280, 820)
        self._build_ui()

    def _build_ui(self) -> None:
        """构建主布局：标题 + 左右分栏。"""

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(14)

        header = QLabel("合同审查系统 GUI 第一版")
        header.setObjectName("SectionTitle")
        root_layout.addWidget(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        root_layout.addWidget(splitter, stretch=1)

        self.setCentralWidget(root)

    def _build_left_panel(self) -> QWidget:
        """构建左侧面板：流程状态与实时日志。"""

        panel = QFrame()
        panel.setObjectName("PanelCard")
        layout = QVBoxLayout(panel)

        status_group = QGroupBox("流程状态")
        status_layout = QVBoxLayout(status_group)
        self.stage_label = QLabel("等待开始")
        self.stage_label.setObjectName("stageLabel")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        status_layout.addWidget(self.stage_label)
        status_layout.addWidget(self.progress_bar)

        log_group = QGroupBox("实时日志")
        log_layout = QVBoxLayout(log_group)
        self.log_view = QTextEdit()
        self.log_view.setObjectName("logView")
        self.log_view.setReadOnly(True)
        log_layout.addWidget(self.log_view)

        layout.addWidget(status_group)
        layout.addWidget(log_group, stretch=1)
        return panel

    def _build_right_panel(self) -> QWidget:
        """构建右侧面板：输入区、执行按钮与输出区。"""

        panel = QFrame()
        panel.setObjectName("PanelCard")
        layout = QVBoxLayout(panel)

        input_group = QGroupBox("输入")
        input_layout = QGridLayout(input_group)
        input_layout.setHorizontalSpacing(10)
        input_layout.setVerticalSpacing(12)
        input_layout.setColumnStretch(0, 0)
        input_layout.setColumnStretch(1, 1)
        input_layout.setColumnStretch(2, 0)

        self.input_path_edit = QLineEdit()
        self.input_path_edit.setObjectName("inputPathEdit")
        browse_button = QPushButton("选择合同")
        browse_button.setObjectName("browseButton")
        browse_button.setMinimumWidth(92)
        browse_button.clicked.connect(self._choose_input_file)

        self.stance_combo = QComboBox()
        self.stance_combo.setObjectName("stanceCombo")
        self.stance_combo.addItem("甲方", "party_a")
        self.stance_combo.addItem("乙方", "party_b")

        self.extra_prompt_edit = QTextEdit()
        self.extra_prompt_edit.setObjectName("extraPromptEdit")
        self.extra_prompt_edit.setPlaceholderText("可补充本次审查重点；不填写时将按默认规则审查。")
        self.extra_prompt_edit.setPlainText(DEFAULT_REMARK_EXAMPLE)
        self.extra_prompt_edit.setMinimumHeight(180)

        input_path_label = QLabel("原合同")
        input_path_label.setMinimumWidth(78)
        stance_label = QLabel("审查立场")
        stance_label.setMinimumWidth(78)
        remark_label = QLabel("备注")
        remark_label.setMinimumWidth(78)
        remark_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        input_layout.addWidget(input_path_label, 0, 0)
        input_layout.addWidget(self.input_path_edit, 0, 1)
        input_layout.addWidget(browse_button, 0, 2)
        input_layout.addWidget(stance_label, 1, 0)
        input_layout.addWidget(self.stance_combo, 1, 1, 1, 2)
        input_layout.addWidget(remark_label, 2, 0)
        input_layout.addWidget(self.extra_prompt_edit, 2, 1, 1, 2)

        action_row = QHBoxLayout()
        self.start_button = QPushButton("开始运行")
        self.start_button.setObjectName("startButton")
        self.start_button.setMinimumWidth(120)
        self.start_button.clicked.connect(self._start_pipeline)
        action_row.addStretch(1)
        action_row.addWidget(self.start_button)

        output_group = QGroupBox("输出")
        output_layout = QGridLayout(output_group)
        output_layout.setHorizontalSpacing(10)
        output_layout.setVerticalSpacing(12)
        output_layout.setColumnStretch(0, 0)
        output_layout.setColumnStretch(1, 1)
        output_layout.setColumnStretch(2, 1)
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setObjectName("outputPathEdit")
        self.output_path_edit.setReadOnly(True)
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setObjectName("outputDirEdit")
        self.output_dir_edit.setReadOnly(True)
        self.open_file_button = QPushButton("打开文件")
        self.open_file_button.setObjectName("openFileButton")
        self.open_file_button.setMinimumWidth(120)
        self.open_file_button.setEnabled(False)
        self.open_file_button.clicked.connect(self._open_output_file)
        self.open_dir_button = QPushButton("打开输出目录")
        self.open_dir_button.setObjectName("openDirButton")
        self.open_dir_button.setMinimumWidth(120)
        self.open_dir_button.setEnabled(False)
        self.open_dir_button.clicked.connect(self._open_output_dir)

        output_file_label = QLabel("批注版 Word")
        output_file_label.setMinimumWidth(110)
        output_dir_label = QLabel("输出目录")
        output_dir_label.setMinimumWidth(110)

        output_layout.addWidget(output_file_label, 0, 0)
        output_layout.addWidget(self.output_path_edit, 0, 1, 1, 2)
        output_layout.addWidget(output_dir_label, 1, 0)
        output_layout.addWidget(self.output_dir_edit, 1, 1, 1, 2)
        output_layout.addWidget(self.open_file_button, 2, 1)
        output_layout.addWidget(self.open_dir_button, 2, 2)

        layout.addWidget(input_group)
        layout.addLayout(action_row)
        layout.addWidget(output_group)
        layout.addStretch(1)
        return panel

    def _choose_input_file(self) -> None:
        """弹出文件选择框并写入输入路径。"""

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择原合同文件",
            str(Path.cwd()),
            "Word files (*.doc *.docx);;All files (*.*)",
        )
        if not file_path:
            return
        self.input_path_edit.setText(file_path)

    def _start_pipeline(self) -> None:
        """收集输入参数并启动后台线程执行任务。"""

        input_path = self.input_path_edit.text().strip()
        if not input_path:
            QMessageBox.warning(self, "缺少输入", "请先选择一个原合同文件。")
            return

        request = GuiReviewRequest(
            input_path=input_path,
            review_stance=str(self.stance_combo.currentData()),
            extra_user_instruction=self.extra_prompt_edit.toPlainText().strip(),
        )

        self.latest_result = None
        self.output_path_edit.clear()
        self.output_dir_edit.clear()
        self.log_view.clear()
        self.progress_bar.setValue(0)
        self.stage_label.setText("准备启动")
        self.open_file_button.setEnabled(False)
        self.open_dir_button.setEnabled(False)
        self._set_inputs_enabled(False)

        # 使用 QThread + QObject worker 模式，避免主线程卡顿。
        self.worker_thread = QThread(self)
        self.worker = PipelineWorker(request, self.service)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.progress_changed.connect(self._on_progress_changed)
        self.worker.log_emitted.connect(self._append_log)
        self.worker.finished.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self._cleanup_worker)
        self.worker_thread.start()

    def _set_inputs_enabled(self, enabled: bool) -> None:
        """统一切换输入控件可用状态。"""

        self.input_path_edit.setEnabled(enabled)
        self.stance_combo.setEnabled(enabled)
        self.extra_prompt_edit.setEnabled(enabled)
        self.start_button.setEnabled(enabled)

    def _cleanup_worker(self) -> None:
        """在线程结束后释放 worker 引用，避免悬挂状态。"""

        self.worker = None
        self.worker_thread = None

    def _on_progress_changed(self, value: int, message: str) -> None:
        """更新进度条和阶段文案。"""

        self.progress_bar.setValue(value)
        self.stage_label.setText(message)

    def _append_log(self, message: str) -> None:
        """将日志追加到日志窗口尾部。"""

        self.log_view.moveCursor(QTextCursor.MoveOperation.End)
        self.log_view.insertHtml(render_log_html(message))
        self.log_view.insertHtml("<br>")
        self.log_view.moveCursor(QTextCursor.MoveOperation.End)

    def _on_finished(self, payload: dict) -> None:
        """处理任务成功回调并刷新输出区域。"""

        self.latest_result = GuiReviewResult(**payload)
        self.output_path_edit.setText(self.latest_result.primary_comment_file)
        self.output_dir_edit.setText(self.latest_result.pipeline_output_dir)
        self.open_file_button.setEnabled(bool(self.latest_result.primary_comment_file))
        self.open_dir_button.setEnabled(True)
        self.stage_label.setText("完成")
        self.progress_bar.setValue(100)
        self._append_log("GUI：任务完成。")
        self._set_inputs_enabled(True)

    def _on_failed(self, message: str) -> None:
        """处理任务失败回调并提示错误。"""

        self.latest_result = None
        self.output_path_edit.clear()
        self.output_dir_edit.clear()
        self.stage_label.setText("失败")
        self._append_log(f"GUI：任务失败：{message}")
        self._set_inputs_enabled(True)
        QMessageBox.critical(self, "运行失败", message)

    def _open_output_file(self) -> None:
        """打开本次运行生成的主批注文件。"""

        if self.latest_result is None or not self.latest_result.primary_comment_file:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.latest_result.primary_comment_file))

    def _open_output_dir(self) -> None:
        """打开本次运行的输出目录。"""

        if self.latest_result is None:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.latest_result.pipeline_output_dir))


def run() -> int:
    """创建并启动 GUI 应用。"""

    app = QApplication([])
    app.setApplicationName("合同审查系统 GUI")
    app.setStyleSheet(APP_STYLESHEET)
    window = ContractReviewMainWindow()
    window.show()
    return app.exec()
