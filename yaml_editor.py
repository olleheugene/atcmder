import os
import yaml
from PySide6.QtWidgets import QDialog, QVBoxLayout, QPlainTextEdit, QPushButton, QLabel, QHBoxLayout, QMessageBox
from PySide6.QtGui import QFont

class YamlEditorDialog(QDialog):
    def __init__(self, yaml_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Predefined Command List (YAML)")
        self.yaml_path = yaml_path

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Editing: {os.path.basename(yaml_path)}"))

        self.editor = QPlainTextEdit(self)
        self.editor.setFont(QFont("Monaco", 11))
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(self.editor)

        # Load YAML
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                self.editor.setPlainText(f.read())
        except Exception:
            self.editor.setPlainText("- index: 0\n  checked: true\n  title:\n    text: ''\n    disabled: false\n  time: 0.5\n")

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save", self)
        cancel_btn = QPushButton("Cancel", self)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        save_btn.clicked.connect(self.save_yaml)
        cancel_btn.clicked.connect(self.reject)
        self.resize(600, 800)

    def save_yaml(self):
        try:
            # Validate YAML
            data = yaml.safe_load(self.editor.toPlainText())
            with open(self.yaml_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Invalid YAML", f"Error: {e}")