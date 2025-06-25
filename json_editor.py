import os
import json
from PySide6.QtWidgets import QDialog, QVBoxLayout, QPlainTextEdit, QPushButton, QLabel, QHBoxLayout, QMessageBox
from PySide6.QtGui import QFont

class JsonEditorDialog(QDialog):
    def __init__(self, json_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Predefined Command List")
        self.json_path = json_path

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Editing: {os.path.basename(json_path)}"))

        self.editor = QPlainTextEdit(self)
        self.editor.setFont(QFont("Monaco", 11))
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(self.editor)

        # Load JSON
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                self.editor.setPlainText(f.read())
        except Exception:
            self.editor.setPlainText("[]")

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save", self)
        cancel_btn = QPushButton("Cancel", self)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        save_btn.clicked.connect(self.save_json)
        cancel_btn.clicked.connect(self.reject)
        self.resize(600, 800)

    def save_json(self):
        try:
            data = json.loads(self.editor.toPlainText())
            with open(self.json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Invalid JSON", f"Error: {e}")