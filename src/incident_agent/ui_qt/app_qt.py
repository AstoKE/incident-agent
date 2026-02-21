from __future__ import annotations

import json
import os
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, List

from PySide6.QtCore import QThread, Signal, Qt, QRegularExpression
from PySide6.QtGui import (
    QIcon,
    QSyntaxHighlighter,
    QTextCharFormat,
    QFont,
)
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QFileDialog,
    QLabel,
    QSpinBox,
    QMessageBox,
    QTextEdit,
    QPlainTextEdit,
    QTabWidget,
    QListWidget,
    QListWidgetItem,
    QSplitter,
)

# ✅ Burayı repo'ndaki gerçek graph builder'a göre ayarla:
# Örn: from incident_agent.graph import build_graph
from incident_agent.graph import build_graph  # <-- gerekirse ismi değiştir


def resource_path(relative: str) -> str:
    """
    PyInstaller --onefile ile bundle edildiğinde dosya yolu çözümü.
    Normal çalışmada: proje içindeki dosyayı döner.
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return str(Path(base) / relative)
    return str(Path(__file__).resolve().parent / relative)


def severity_style(sev: str) -> str:
    """
    Severity badge için basit renk paleti (dark UI uyumlu).
    """
    s = (sev or "").upper()
    if s in ("CRITICAL", "FATAL", "PANIC"):
        return "background:#7f1d1d;color:#fff;border:1px solid #ef4444;"
    if s in ("HIGH",):
        return "background:#7c2d12;color:#fff;border:1px solid #fb923c;"
    if s in ("MEDIUM", "WARN", "WARNING"):
        return "background:#713f12;color:#fff;border:1px solid #facc15;"
    if s in ("LOW", "INFO"):
        return "background:#14532d;color:#fff;border:1px solid #22c55e;"
    return "background:#111827;color:#fff;border:1px solid #374151;"


def to_markdown_report(result: Dict[str, Any]) -> str:
    sev = result.get("severity", "")
    error_count = result.get("error_count", 0)
    services = result.get("services", [])
    top_events = result.get("top_events", [])
    summary = result.get("summary", "")
    root_causes = result.get("likely_root_causes", []) or []
    actions = result.get("immediate_actions", []) or []
    questions = result.get("questions_for_human", []) or []

    def bullets(xs: List[str]) -> str:
        if not xs:
            return "- (none)"
        return "\n".join([f"- {x}" for x in xs])

    return (
        "# Incident Report\n\n"
        f"**Severity:** {sev}\n\n"
        f"**Error Count:** {error_count}\n\n"
        f"**Services:** {services}\n\n"
        f"**Top Events:** {top_events}\n\n"
        "## Summary\n"
        f"{summary}\n\n"
        "## Likely Root Causes\n"
        f"{bullets(root_causes)}\n\n"
        "## Immediate Actions (Runbook)\n"
        f"{bullets(actions)}\n\n"
        "## Questions for Human\n"
        f"{bullets(questions)}\n"
    )


class LogHighlighter(QSyntaxHighlighter):
    """
    Raw logs içinde anahtar kelime renklendirme.
    (Performans için QSyntaxHighlighter kullanıyoruz.)
    """
    def __init__(self, doc):
        super().__init__(doc)

        def fmt(bold: bool = False) -> QTextCharFormat:
            f = QTextCharFormat()
            if bold:
                f.setFontWeight(QFont.Bold)
            return f

        self.rules: list[tuple[QRegularExpression, QTextCharFormat]] = []

        # CRITICAL / FATAL / PANIC
        f_crit = fmt(True)
        f_crit.setForeground(Qt.red)
        self.rules.append((QRegularExpression(r"\b(CRITICAL|FATAL|PANIC)\b"), f_crit))

        # ERROR/FAILED/EXCEPTION
        f_err = fmt(True)
        f_err.setForeground(Qt.red)
        self.rules.append((QRegularExpression(r"\b(ERROR|FAILED|FAILURE|EXCEPTION|TRACEBACK)\b"), f_err))

        # WARN
        f_warn = fmt(True)
        f_warn.setForeground(Qt.yellow)
        self.rules.append((QRegularExpression(r"\b(WARN|WARNING)\b"), f_warn))

        # INFO
        f_info = fmt(False)
        f_info.setForeground(Qt.green)
        self.rules.append((QRegularExpression(r"\bINFO\b"), f_info))

        # Common incident-ish keywords
        f_kw = fmt(True)
        f_kw.setForeground(Qt.cyan)
        self.rules.append((QRegularExpression(r"\b(incident|root cause|rca|runbook|dedup|severity)\b", QRegularExpression.CaseInsensitiveOption), f_kw))

        # Event-like tokens (istersen burayı genişlet)
        f_evt = fmt(True)
        f_evt.setForeground(Qt.cyan)
        self.rules.append((
            QRegularExpression(
                r"\b(authentication_failed|db_connection_refused|payment_gateway_down|redis_client_not_open|null_pointer_exception|timeout|rate_limit|connection refused)\b",
                QRegularExpression.CaseInsensitiveOption,
            ),
            f_evt,
        ))

    def highlightBlock(self, text: str):
        for rx, f in self.rules:
            it = rx.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), f)


@dataclass
class AnalyzeParams:
    path: str
    window_lines: int


class AnalyzeWorker(QThread):
    finished_ok = Signal(dict)   # result dict
    finished_err = Signal(str)   # error text

    def __init__(self, params: AnalyzeParams):
        super().__init__()
        self.params = params

    def run(self):
        try:
            graph = build_graph()
            init_state: Dict[str, Any] = {
                "log_path": self.params.path,
                "window_lines": int(self.params.window_lines),
            }
            out = graph.invoke(init_state)
            self.finished_ok.emit(dict(out))
        except Exception:
            self.finished_err.emit(traceback.format_exc())


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("incident-agent (ollama 3.1)")

        # ✅ App icon (pencere icon)
        try:
            self.setWindowIcon(QIcon(resource_path("assets/app.ico")))
        except Exception:
            pass

        self.resize(1100, 750)

        self.selected_path: Optional[str] = None
        self.worker: Optional[AnalyzeWorker] = None
        self.last_result: Dict[str, Any] = {}

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        # ===== Top controls =====
        row = QHBoxLayout()

        btn_pick = QPushButton("Log Seç")
        btn_pick.clicked.connect(self.pick_file)

        self.path_label = QLabel("Dosya seçilmedi.")
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.spin_lines = QSpinBox()
        self.spin_lines.setRange(10, 5000)
        self.spin_lines.setValue(200)
        self.spin_lines.setSingleStep(50)

        self.btn_analyze = QPushButton("Analyze")
        self.btn_analyze.setEnabled(False)
        self.btn_analyze.clicked.connect(self.analyze)

        row.addWidget(btn_pick)
        row.addWidget(self.path_label, 1)
        row.addWidget(QLabel("Last N lines:"))
        row.addWidget(self.spin_lines)
        row.addWidget(self.btn_analyze)
        layout.addLayout(row)

        # ===== Tabs =====
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        # --- Summary tab (badge + buttons + text) ---
        self.summary_tab = QWidget()
        summary_layout = QVBoxLayout(self.summary_tab)

        summary_header = QHBoxLayout()
        self.sev_badge = QLabel("Severity: -")
        self.sev_badge.setStyleSheet(
            "padding:6px 10px;border-radius:10px;"
            "background:#111827;color:#fff;border:1px solid #374151;"
        )

        btn_copy_summary = QPushButton("Copy Summary")
        btn_copy_summary.clicked.connect(self.copy_summary)

        btn_export_md = QPushButton("Export MD")
        btn_export_md.clicked.connect(self.export_markdown)

        btn_export_json = QPushButton("Export JSON")
        btn_export_json.clicked.connect(self.export_json)

        summary_header.addWidget(self.sev_badge)
        summary_header.addStretch(1)
        summary_header.addWidget(btn_copy_summary)
        summary_header.addWidget(btn_export_md)
        summary_header.addWidget(btn_export_json)
        summary_layout.addLayout(summary_header)

        self.txt_summary = QTextEdit()
        self.txt_summary.setReadOnly(True)
        self.txt_summary.setAcceptRichText(False)
        summary_layout.addWidget(self.txt_summary, 1)

        # --- Actions tab (checklist + copy) ---
        self.actions_tab = QWidget()
        actions_layout = QVBoxLayout(self.actions_tab)

        actions_header = QHBoxLayout()
        actions_header.addWidget(QLabel("Immediate Actions (Runbook)"))
        actions_header.addStretch(1)
        btn_copy_actions = QPushButton("Copy Actions")
        btn_copy_actions.clicked.connect(self.copy_actions)
        actions_header.addWidget(btn_copy_actions)
        actions_layout.addLayout(actions_header)

        self.actions_list = QListWidget()
        actions_layout.addWidget(self.actions_list, 1)

        # --- Questions tab (list + copy) ---
        self.questions_tab = QWidget()
        questions_layout = QVBoxLayout(self.questions_tab)

        questions_header = QHBoxLayout()
        questions_header.addWidget(QLabel("Questions for Human"))
        questions_header.addStretch(1)
        btn_copy_questions = QPushButton("Copy Questions")
        btn_copy_questions.clicked.connect(self.copy_questions)
        questions_header.addWidget(btn_copy_questions)
        questions_layout.addLayout(questions_header)

        self.questions_list = QListWidget()
        questions_layout.addWidget(self.questions_list, 1)

        # --- Raw tab (highlighter) ---
        self.raw_tab = QWidget()
        raw_layout = QVBoxLayout(self.raw_tab)

        raw_header = QHBoxLayout()
        raw_header.addWidget(QLabel("Raw Logs (last N)"))
        raw_header.addStretch(1)
        btn_copy_raw = QPushButton("Copy Raw")
        btn_copy_raw.clicked.connect(self.copy_raw)
        raw_header.addWidget(btn_copy_raw)
        raw_layout.addLayout(raw_header)

        self.txt_raw = QPlainTextEdit()
        self.txt_raw.setReadOnly(True)
        raw_layout.addWidget(self.txt_raw, 1)
        self.raw_highlighter = LogHighlighter(self.txt_raw.document())

        # --- Full JSON tab ---
        self.json_tab = QWidget()
        json_layout = QVBoxLayout(self.json_tab)

        json_header = QHBoxLayout()
        json_header.addWidget(QLabel("Full JSON"))
        json_header.addStretch(1)
        btn_copy_json = QPushButton("Copy JSON")
        btn_copy_json.clicked.connect(self.copy_json)
        json_header.addWidget(btn_copy_json)
        json_layout.addLayout(json_header)

        self.txt_json = QPlainTextEdit()
        self.txt_json.setReadOnly(True)
        json_layout.addWidget(self.txt_json, 1)

        # Add tabs
        self.tabs.addTab(self.summary_tab, "Summary")
        self.tabs.addTab(self.actions_tab, "Actions")
        self.tabs.addTab(self.questions_tab, "Questions")
        self.tabs.addTab(self.raw_tab, "Raw last N")
        self.tabs.addTab(self.json_tab, "Full JSON")

    # ---------------- UI helpers ----------------
    def _clipboard_set(self, text: str):
        QApplication.clipboard().setText(text or "")

    def _fill_checklist(self, listw: QListWidget, items: List[str], checkable: bool = True):
        listw.clear()
        for s in (items or []):
            it = QListWidgetItem(str(s))
            if checkable:
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Unchecked)
            listw.addItem(it)

    # ---------------- actions for buttons ----------------
    def copy_summary(self):
        if not self.last_result:
            return
        self._clipboard_set(self.last_result.get("summary", "") or "")

    def copy_actions(self):
        xs = self.last_result.get("immediate_actions", []) or []
        self._clipboard_set("\n".join([str(x) for x in xs]))

    def copy_questions(self):
        xs = self.last_result.get("questions_for_human", []) or []
        self._clipboard_set("\n".join([str(x) for x in xs]))

    def copy_raw(self):
        self._clipboard_set(self.txt_raw.toPlainText())

    def copy_json(self):
        self._clipboard_set(self.txt_json.toPlainText())

    def export_markdown(self):
        if not self.last_result:
            QMessageBox.information(self, "Export", "Henüz analiz sonucu yok.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Markdown kaydet", "incident_report.md", "Markdown (*.md)")
        if not path:
            return
        md = to_markdown_report(self.last_result)
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
        QMessageBox.information(self, "Export", f"Kaydedildi:\n{path}")

    def export_json(self):
        if not self.last_result:
            QMessageBox.information(self, "Export", "Henüz analiz sonucu yok.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "JSON kaydet", "incident_result.json", "JSON (*.json)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.last_result, f, ensure_ascii=False, indent=2)
        QMessageBox.information(self, "Export", f"Kaydedildi:\n{path}")

    # ---------------- main workflow ----------------
    def pick_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Log dosyası seç",
            "",
            "Log Files (*.log *.txt *.jsonl *.json);;All Files (*)",
        )
        if not path:
            return
        self.selected_path = path
        self.path_label.setText(path)
        self.btn_analyze.setEnabled(True)

    def analyze(self):
        if not self.selected_path:
            return

        self.btn_analyze.setEnabled(False)
        self.btn_analyze.setText("Analyzing...")

        params = AnalyzeParams(path=self.selected_path, window_lines=self.spin_lines.value())
        self.worker = AnalyzeWorker(params)
        self.worker.finished_ok.connect(self.on_ok)
        self.worker.finished_err.connect(self.on_err)
        self.worker.start()

    def on_ok(self, result: dict):
        self.last_result = result or {}

        # Key fields
        severity = str(result.get("severity", "") or "").upper()
        error_count = result.get("error_count", 0)
        services = result.get("services", [])
        top_events = result.get("top_events", [])

        summary = result.get("summary", "") or ""
        root_causes = result.get("likely_root_causes", []) or []
        actions = result.get("immediate_actions", []) or []
        questions = result.get("questions_for_human", []) or []
        last_n_raw = result.get("last_n_raw", [])

        # Severity badge
        self.sev_badge.setText(f"Severity: {severity or '-'}")
        self.sev_badge.setStyleSheet("padding:6px 10px;border-radius:10px;" + severity_style(severity))

        # Summary body (daha okunur format)
        summary_text = (
            f"Severity: {severity}\n"
            f"Error Count: {error_count}\n"
            f"Services: {services}\n"
            f"Top Events: {top_events}\n\n"
            f"Summary:\n{summary}\n\n"
            "Likely Root Causes:\n"
        )
        if root_causes:
            summary_text += "\n".join([f"- {x}" for x in root_causes])
        else:
            summary_text += "- (none)"

        self.txt_summary.setPlainText(summary_text)

        # Actions / Questions lists
        self._fill_checklist(self.actions_list, [str(x) for x in actions], checkable=True)
        self._fill_checklist(self.questions_list, [str(x) for x in questions], checkable=False)

        # Raw last N
        if isinstance(last_n_raw, list):
            self.txt_raw.setPlainText("\n".join([str(x) for x in last_n_raw]))
        else:
            self.txt_raw.setPlainText(str(last_n_raw))

        # Full JSON
        self.txt_json.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))

        self.btn_analyze.setEnabled(True)
        self.btn_analyze.setText("Analyze")

    def on_err(self, err: str):
        QMessageBox.critical(self, "Analyze Error", err)
        self.btn_analyze.setEnabled(True)
        self.btn_analyze.setText("Analyze")


def main():
    app = QApplication([])
    w = MainWindow()
    w.show()
    app.exec()


if __name__ == "__main__":
    main()