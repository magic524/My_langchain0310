"""Qt stylesheet for the first GUI version."""

from __future__ import annotations


APP_STYLESHEET = """
QWidget {
    background: #f7f6f3;
    color: #24323d;
    font-family: "Microsoft YaHei UI";
    font-size: 13px;
}
QFrame#PanelCard {
    background: #ffffff;
    border: 1px solid #d8dde3;
    border-radius: 14px;
}
QLabel#SectionTitle {
    font-size: 16px;
    font-weight: 700;
}
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {
    background: #ffffff;
    border: 1px solid #cfd6dd;
    border-radius: 10px;
    padding: 8px;
}
QPushButton {
    background: #2f6f95;
    color: #ffffff;
    border: none;
    border-radius: 10px;
    padding: 8px 16px;
    font-weight: 600;
}
QPushButton:hover {
    background: #255c7c;
}
QPushButton:disabled {
    background: #b7c2cb;
}
QProgressBar {
    border: 1px solid #d1d7de;
    border-radius: 8px;
    background: #eef2f5;
    text-align: center;
}
QProgressBar::chunk {
    border-radius: 7px;
    background: #4d9a6d;
}
QGroupBox {
    font-weight: 700;
    border: 1px solid #dde2e7;
    border-radius: 12px;
    margin-top: 12px;
    padding-top: 12px;
    background: #ffffff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}
"""
