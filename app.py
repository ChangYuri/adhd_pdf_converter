"""
Bionic PDF — desktop GUI (PyQt6)
Drag and drop a PDF to apply bionic reading formatting.
"""

import subprocess
from pathlib import Path

from PyQt6.QtCore import QEvent, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from processor import process_pdf


# ---------------------------------------------------------------------------
# Stylesheet
# ---------------------------------------------------------------------------

APP_STYLE = """
QWidget {
    background-color: #F2F2F7;
    font-family: -apple-system, 'Helvetica Neue', Arial, sans-serif;
    color: #1C1C1E;
}

/* Drop zone card */
QFrame#drop_zone {
    background-color: #FFFFFF;
    border: 2px dashed #C7C7CC;
    border-radius: 14px;
}
QFrame#drop_zone[hovered=true] {
    border-color: #007AFF;
    background-color: #F0F7FF;
}

/* "or browse" inline link */
QPushButton#browse_link {
    background: transparent;
    color: #007AFF;
    border: none;
    font-size: 12px;
    padding: 0;
}
QPushButton#browse_link:hover  { color: #0055CC; }
QPushButton#browse_link:disabled { color: #C7C7CC; }

/* Primary action button */
QPushButton#open_btn {
    background-color: #007AFF;
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
    padding: 0 24px;
}
QPushButton#open_btn:hover   { background-color: #0066EE; }
QPushButton#open_btn:pressed { background-color: #0051C3; }

/* Progress bar */
QProgressBar {
    background-color: #E5E5EA;
    border: none;
    border-radius: 3px;
}
QProgressBar::chunk {
    background-color: #007AFF;
    border-radius: 3px;
}
"""


# ---------------------------------------------------------------------------
# Worker thread
# ---------------------------------------------------------------------------

class Worker(QThread):
    progress = pyqtSignal(float)
    finished = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(self, input_path: str):
        super().__init__()
        self.input_path = input_path

    def run(self):
        try:
            out = process_pdf(self.input_path, progress_callback=self.progress.emit)
            self.finished.emit(str(out))
        except Exception as e:
            self.error.emit(str(e))


# ---------------------------------------------------------------------------
# Drop zone widget
# ---------------------------------------------------------------------------

class DropZone(QFrame):
    file_dropped = pyqtSignal(str)

    def __init__(self, browse_callback):
        super().__init__()
        self.setObjectName("drop_zone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(148)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(4)
        layout.setContentsMargins(20, 24, 20, 24)

        self.icon_label = QLabel("↓")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setFont(QFont("-apple-system", 26))
        self.icon_label.setStyleSheet("color: #C7C7CC; border: none; background: transparent;")

        self.main_label = QLabel("Drop a PDF here")
        self.main_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_label.setFont(QFont("-apple-system", 14, QFont.Weight.DemiBold))
        self.main_label.setStyleSheet("color: #3A3A3C; border: none; background: transparent;")

        self.browse_btn = QPushButton("or browse")
        self.browse_btn.setObjectName("browse_link")
        self.browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.browse_btn.setFixedHeight(20)
        self.browse_btn.clicked.connect(browse_callback)

        layout.addWidget(self.icon_label)
        layout.addWidget(self.main_label)
        layout.addWidget(self.browse_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # Forward drag events from child widgets to this frame
        for child in self.findChildren(QWidget):
            child.installEventFilter(self)

    def eventFilter(self, obj, event):
        t = event.type()
        if t == QEvent.Type.DragEnter:
            self.dragEnterEvent(event)
            return True
        if t == QEvent.Type.DragLeave:
            self.dragLeaveEvent(event)
            return True
        if t == QEvent.Type.Drop:
            self.dropEvent(event)
            return True
        return False

    def _set_hovered(self, state: bool):
        self.setProperty("hovered", state)
        self.style().unpolish(self)
        self.style().polish(self)
        icon_color = "#007AFF" if state else "#C7C7CC"
        self.icon_label.setStyleSheet(
            f"color: {icon_color}; border: none; background: transparent;"
        )

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_hovered(True)

    def dragLeaveEvent(self, event):
        self._set_hovered(False)

    def dropEvent(self, event):
        self._set_hovered(False)
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            self.file_dropped.emit(path if path.lower().endswith(".pdf") else "")


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bionic PDF")
        self.setFixedSize(440, 340)
        self._output_path: str | None = None
        self._worker:      Worker | None = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 22)
        root.setSpacing(0)

        # --- Header ---
        title = QLabel("Bionic PDF")
        title.setFont(QFont("-apple-system", 17, QFont.Weight.Bold))
        title.setStyleSheet("color: #1C1C1E;")

        subtitle = QLabel("Read faster, focus better")
        subtitle.setFont(QFont("-apple-system", 11))
        subtitle.setStyleSheet("color: #8E8E93;")

        root.addWidget(title)
        root.addWidget(subtitle)
        root.addSpacing(16)

        # --- Drop zone ---
        self.drop_zone = DropZone(browse_callback=self._browse)
        self.drop_zone.file_dropped.connect(self._handle_path)
        root.addWidget(self.drop_zone)
        root.addSpacing(14)

        # --- Progress bar (hidden until processing) ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.hide()
        root.addWidget(self.progress_bar)
        root.addSpacing(8)

        # --- Status label ---
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setFont(QFont("-apple-system", 11))
        self.status_label.setStyleSheet("color: #8E8E93;")
        self.status_label.setFixedHeight(18)
        root.addWidget(self.status_label)
        root.addSpacing(10)

        # --- Open Result button (hidden until done) ---
        self.open_btn = QPushButton("Open Result")
        self.open_btn.setObjectName("open_btn")
        self.open_btn.setFixedHeight(36)
        self.open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_btn.clicked.connect(self._open_result)
        self.open_btn.hide()
        root.addWidget(self.open_btn)

        root.addStretch()

    # -----------------------------------------------------------------------
    # Handlers
    # -----------------------------------------------------------------------

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select a PDF", "", "PDF files (*.pdf)"
        )
        if path:
            self._start_processing(path)

    def _handle_path(self, path: str):
        if not path:
            self._set_status("Please drop a PDF file.", error=True)
            return
        self._start_processing(path)

    def _start_processing(self, input_path: str):
        self._output_path = None
        self.open_btn.hide()
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self._set_status(f"Processing  {Path(input_path).name}…")
        self.drop_zone.browse_btn.setEnabled(False)

        self._worker = Worker(input_path)
        self._worker.progress.connect(lambda v: self.progress_bar.setValue(int(v * 100)))
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_done(self, output_path: str):
        self._output_path = output_path
        self.progress_bar.setValue(100)
        self._set_status(f"Saved as  {Path(output_path).name}")
        self.open_btn.show()
        self.drop_zone.browse_btn.setEnabled(True)

    def _on_error(self, msg: str):
        self.progress_bar.hide()
        self._set_status(f"Error: {msg}", error=True)
        self.drop_zone.browse_btn.setEnabled(True)

    def _set_status(self, text: str, error: bool = False):
        color = "#FF3B30" if error else "#8E8E93"
        self.status_label.setStyleSheet(f"color: {color};")
        self.status_label.setText(text)

    def _open_result(self):
        if self._output_path:
            subprocess.run(["open", self._output_path])


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLE)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
