"""合同审查系统 GUI 的 CRSv1 窗口实现。"""

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
    progress_changed = pyqtSignal(int, str)
    log_emitted = pyqtSignal(str)
    finished = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, request: GuiReviewRequest, service: GuiPipelineService) -> None:
        super().__init__()
        self.request = request
        self.service = service

    def run(self) -> None:
        try:
            result = self.service.run(
                self.request,
                progress_callback=self.progress_changed.emit,
                log_callback=self.log_emitted.emit,
            )
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
            return
        self.finished.emit(asdict(result))


class ContractReviewMainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.service = GuiPipelineService()
        self.worker_thread: QThread | None = None
        self.worker: PipelineWorker | None = None
        self.latest_result: GuiReviewResult | None = None

        self.setWindowTitle("合同审查系统 GUI - CRSv1")
        self.resize(1280, 820)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(14)

        header = QLabel("合同审查系统 GUI - CRSv1")
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
        panel = QFrame()
        panel.setObjectName("PanelCard")
        layout = QVBoxLayout(panel)

        status_group = QGroupBox("流程状态")
        status_layout = QVBoxLayout(status_group)
        self.stage_label = QLabel("等待开始")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        status_layout.addWidget(self.stage_label)
        status_layout.addWidget(self.progress_bar)

        log_group = QGroupBox("实时日志")
        log_layout = QVBoxLayout(log_group)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        log_layout.addWidget(self.log_view)

        layout.addWidget(status_group)
        layout.addWidget(log_group, stretch=1)
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("PanelCard")
        layout = QVBoxLayout(panel)

        input_group = QGroupBox("输入")
        input_layout = QGridLayout(input_group)
        input_layout.setHorizontalSpacing(10)
        input_layout.setVerticalSpacing(12)
        input_layout.setColumnStretch(1, 1)

        self.input_path_edit = QLineEdit()
        browse_button = QPushButton("选择合同")
        browse_button.clicked.connect(self._choose_input_file)

        self.stance_combo = QComboBox()
        self.stance_combo.addItem("甲方", "party_a")
        self.stance_combo.addItem("乙方", "party_b")

        self.extra_prompt_edit = QTextEdit()
        self.extra_prompt_edit.setPlaceholderText("可补充本次审查重点；不填写时按默认规则审查。")
        self.extra_prompt_edit.setPlainText(DEFAULT_REMARK_EXAMPLE)
        self.extra_prompt_edit.setMinimumHeight(180)

        input_layout.addWidget(QLabel("原合同"), 0, 0)
        input_layout.addWidget(self.input_path_edit, 0, 1)
        input_layout.addWidget(browse_button, 0, 2)
        input_layout.addWidget(QLabel("审查立场"), 1, 0)
        input_layout.addWidget(self.stance_combo, 1, 1, 1, 2)
        remark_label = QLabel("备注")
        remark_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        input_layout.addWidget(remark_label, 2, 0)
        input_layout.addWidget(self.extra_prompt_edit, 2, 1, 1, 2)

        action_row = QHBoxLayout()
        self.start_button = QPushButton("开始运行")
        self.start_button.clicked.connect(self._start_pipeline)
        action_row.addStretch(1)
        action_row.addWidget(self.start_button)

        output_group = QGroupBox("输出")
        output_layout = QGridLayout(output_group)
        output_layout.setHorizontalSpacing(10)
        output_layout.setVerticalSpacing(12)
        output_layout.setColumnStretch(1, 1)

        self.output_path_edit = QLineEdit()
        self.output_path_edit.setReadOnly(True)
        self.report_path_edit = QLineEdit()
        self.report_path_edit.setReadOnly(True)
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setReadOnly(True)

        self.open_file_button = QPushButton("打开批注 Word")
        self.open_file_button.setEnabled(False)
        self.open_file_button.clicked.connect(self._open_output_file)
        self.open_report_button = QPushButton("打开报告")
        self.open_report_button.setEnabled(False)
        self.open_report_button.clicked.connect(self._open_report_file)
        self.open_dir_button = QPushButton("打开输出目录")
        self.open_dir_button.setEnabled(False)
        self.open_dir_button.clicked.connect(self._open_output_dir)

        output_layout.addWidget(QLabel("批注版 Word"), 0, 0)
        output_layout.addWidget(self.output_path_edit, 0, 1, 1, 2)
        output_layout.addWidget(QLabel("审查报告"), 1, 0)
        output_layout.addWidget(self.report_path_edit, 1, 1, 1, 2)
        output_layout.addWidget(QLabel("输出目录"), 2, 0)
        output_layout.addWidget(self.output_dir_edit, 2, 1, 1, 2)
        output_layout.addWidget(self.open_file_button, 3, 1)
        output_layout.addWidget(self.open_report_button, 3, 2)
        output_layout.addWidget(self.open_dir_button, 4, 1, 1, 2)

        layout.addWidget(input_group)
        layout.addLayout(action_row)
        layout.addWidget(output_group)
        layout.addStretch(1)
        return panel

    def _choose_input_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择原合同文件",
            str(Path.cwd()),
            "Contract files (*.doc *.docx *.pdf);;All files (*.*)",
        )
        if file_path:
            self.input_path_edit.setText(file_path)

    def _start_pipeline(self) -> None:
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
        self.report_path_edit.clear()
        self.output_dir_edit.clear()
        self.log_view.clear()
        self.progress_bar.setValue(0)
        self.stage_label.setText("准备启动")
        self.open_file_button.setEnabled(False)
        self.open_report_button.setEnabled(False)
        self.open_dir_button.setEnabled(False)
        self._set_inputs_enabled(False)

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
        self.input_path_edit.setEnabled(enabled)
        self.stance_combo.setEnabled(enabled)
        self.extra_prompt_edit.setEnabled(enabled)
        self.start_button.setEnabled(enabled)

    def _cleanup_worker(self) -> None:
        self.worker = None
        self.worker_thread = None

    def _on_progress_changed(self, value: int, message: str) -> None:
        self.progress_bar.setValue(value)
        self.stage_label.setText(message)

    def _append_log(self, message: str) -> None:
        self.log_view.moveCursor(QTextCursor.MoveOperation.End)
        self.log_view.insertHtml(render_log_html(message))
        self.log_view.insertHtml("<br>")
        self.log_view.moveCursor(QTextCursor.MoveOperation.End)

    def _on_finished(self, payload: dict) -> None:
        self.latest_result = GuiReviewResult(**payload)
        self.output_path_edit.setText(self.latest_result.primary_comment_file)
        self.report_path_edit.setText(self.latest_result.primary_report_path)
        self.output_dir_edit.setText(self.latest_result.pipeline_output_dir)
        self.open_file_button.setEnabled(bool(self.latest_result.primary_comment_file))
        self.open_report_button.setEnabled(bool(self.latest_result.primary_report_path))
        self.open_dir_button.setEnabled(True)
        self.stage_label.setText("完成")
        self.progress_bar.setValue(100)
        self._append_log("GUI：任务完成。")
        self._set_inputs_enabled(True)

    def _on_failed(self, message: str) -> None:
        self.latest_result = None
        self.output_path_edit.clear()
        self.report_path_edit.clear()
        self.output_dir_edit.clear()
        self.stage_label.setText("失败")
        self._append_log(f"GUI：任务失败：{message}")
        self._set_inputs_enabled(True)
        QMessageBox.critical(self, "运行失败", message)

    def _open_output_file(self) -> None:
        if self.latest_result is None or not self.latest_result.primary_comment_file:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.latest_result.primary_comment_file))

    def _open_report_file(self) -> None:
        if self.latest_result is None or not self.latest_result.primary_report_path:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.latest_result.primary_report_path))

    def _open_output_dir(self) -> None:
        if self.latest_result is None:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.latest_result.pipeline_output_dir))


def run() -> int:
    app = QApplication([])
    app.setApplicationName("合同审查系统 GUI")
    app.setStyleSheet(APP_STYLESHEET)
    window = ContractReviewMainWindow()
    window.show()
    return app.exec()
