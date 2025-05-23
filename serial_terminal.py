import sys
import os
import serial
import threading
import time
import json
import re
import pyte
from PySide6.QtWidgets import (
    QMainWindow, QTextEdit, QLineEdit, QPushButton, QVBoxLayout, QWidget, QHBoxLayout, QCheckBox, QComboBox, QLabel, QGroupBox, QSizePolicy, QMessageBox, QSplitter, QApplication
)
from PySide6.QtGui import QIcon, QFont, QTextCursor, QAction
from PySide6.QtCore import Signal, Qt, QEvent, QTimer
from ansi2html import Ansi2HTMLConverter
from config import get_resources, USER_COMMAND_LIST, USER_PORT_LIST

# Helper for serial port listing
import serial.tools.list_ports
def list_serial_ports():
    return [port.device for port in serial.tools.list_ports.comports()]

class SerialTerminal(QMainWindow):
    serial_data_signal = Signal(str)

    def __init__(self, port=None, baudrate=115200):
        super().__init__()
        self.setWindowTitle("AT Commander v0.7")
        self.resize(1100, 600)
        program_icon_path = get_resources("app_icon.png")
        self.data_buffer = ""
        self.buffer_timeout = None
        self.command_history = []
        self.history_index = -1
        self.current_input_buffer = ""
        if os.path.exists(program_icon_path):
            self.setWindowIcon(QIcon(program_icon_path))
        self.comport_settings = []
        self.recent_ports = self.load_recent_ports()
        self.selected_port = port or ""
        self.baudrate = baudrate
        self.status = self.statusBar()
        self.update_status_bar("Disconnected")
        self.author_label = QLabel("By OllehEugene with AI")
        self.author_label.setStyleSheet("color: #888; margin-left: 12px;")
        self.status.addPermanentWidget(self.author_label)
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        help_menu = menubar.addMenu("Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)
        theme_menu = menubar.addMenu("Theme")
        light_action = QAction("Light", self)
        dark_action = QAction("Dark", self)
        default_action = QAction("Default", self)
        light_action.triggered.connect(lambda: self.apply_theme("light.css"))
        dark_action.triggered.connect(lambda: self.apply_theme("dark.css"))
        default_action.triggered.connect(lambda: self.apply_theme("default"))
        theme_menu.addAction(light_action)
        theme_menu.addAction(dark_action)
        theme_menu.addAction(default_action)
        self.screen = pyte.Screen(120, 40)
        self.stream = pyte.Stream(self.screen)
        self.left_widget = QWidget()
        self.left_layout = QVBoxLayout()
        serial_group = QGroupBox("Serial Settings")
        serial_group_layout = QVBoxLayout()
        self.serial_port_combo = QComboBox()
        self.serial_port_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        port_layout = QHBoxLayout()
        port_label = QLabel("Port:")
        port_layout.addWidget(port_label)
        port_layout.addWidget(self.serial_port_combo)
        serial_group_layout.addLayout(port_layout)
        self.serial_port_combo.currentTextChanged.connect(self.on_port_changed)
        baud_btn_layout = QHBoxLayout()
        self.baudrate_combo = QComboBox()
        baudrates = ["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600", "1000000"]
        self.baudrate_combo.addItems(baudrates)
        self.baudrate_combo.setCurrentText(str(self.baudrate))
        self.baudrate_combo.currentTextChanged.connect(self.on_baudrate_changed)
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setCheckable(True)
        self.connect_btn.clicked.connect(self.toggle_serial_connection)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_serial_ports)
        baud_btn_layout.addWidget(QLabel("Baudrate:"))
        baud_btn_layout.addWidget(self.baudrate_combo)
        baud_btn_layout.addWidget(self.connect_btn)
        baud_btn_layout.addWidget(self.refresh_btn)
        serial_group_layout.addLayout(baud_btn_layout)
        serial_group.setLayout(serial_group_layout)
        self.left_layout.addWidget(serial_group)
        self.checkboxes = []
        self.lineedits = []
        self.sendline_btns = []
        for i in range(10):
            row_widget = QWidget()
            row_layout = QHBoxLayout()
            checkbox = QCheckBox()
            lineedit = QLineEdit()
            lineedit.setAlignment(Qt.AlignCenter) 
            send_btn = QPushButton("Send")
            send_btn.clicked.connect(lambda _, idx=i: self.send_lineedit_command(idx))
            checkbox.stateChanged.connect(lambda _, idx=i: self.save_checkbox_lineedit_to_json(USER_COMMAND_LIST))
            lineedit.textChanged.connect(lambda _, idx=i: self.save_checkbox_lineedit_to_json(USER_COMMAND_LIST))
            row_layout.addWidget(checkbox)
            row_layout.addWidget(lineedit)
            row_layout.addWidget(send_btn)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_widget.setLayout(row_layout)
            self.left_layout.addWidget(row_widget)
            self.checkboxes.append(checkbox)
            self.lineedits.append(lineedit)
            self.sendline_btns.append(send_btn)
        self.left_layout.addStretch()
        self.left_widget.setLayout(self.left_layout)
        self.textedit = QTextEdit()
        self.textedit.setReadOnly(False)
        self.textedit.installEventFilter(self)
        fixed_font = QFont("Courier New")
        fixed_font.setStyleHint(QFont.Monospace)
        self.textedit.setFont(fixed_font)
        self.textedit.document().setMaximumBlockCount(0)
        self.clear_btn = QPushButton()
        self.clear_btn.setIcon(QIcon(get_resources("clear.png")))
        self.clear_btn.setFixedSize(24, 24)
        self.clear_btn.setToolTip("Clean terminal window")
        self.clear_btn.clicked.connect(self.clear_terminal)
        textedit_layout = QVBoxLayout()
        textedit_layout.setContentsMargins(0, 0, 8, 12)
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 8, 4)
        btn_layout.addStretch()
        btn_layout.addWidget(self.clear_btn)
        textedit_layout.addLayout(btn_layout)
        textedit_layout.addWidget(self.textedit)
        right_widget = QWidget()
        right_widget.setLayout(textedit_layout)
        self.toggle_btn = QPushButton()
        self.toggle_btn.setFixedWidth(24)
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setToolTip("Expand/Collapse the terminal window")
        self.toggle_btn.setIcon(QIcon(get_resources("left-3arrow.png")))
        self.toggle_btn.clicked.connect(self.toggle_left_panel)
        btn_widget = QWidget()
        btn_layout = QVBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.addStretch()
        btn_layout.addWidget(self.toggle_btn)
        btn_layout.addStretch()
        btn_widget.setLayout(btn_layout)
        splitter = QSplitter()
        splitter.addWidget(self.left_widget)
        splitter.addWidget(btn_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([250, 24, 850])
        central = QWidget()
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(splitter)
        central.setLayout(main_layout)
        self.setCentralWidget(central)
        self.splitter = splitter
        self.left_panel_visible = True
        self.serial = None
        self.running = False
        self.thread = None
        self.serial_data_signal.connect(self.update_terminal)
        self.ansi_conv = Ansi2HTMLConverter(inline=True, scheme='xterm')
        self.load_checkbox_lineedit_from_json(USER_COMMAND_LIST)
        self.sequential_btn = QPushButton("Sequential Send")
        self.sequential_btn.clicked.connect(self.sequential_send_commands)
        self.left_layout.addWidget(self.sequential_btn)
        self.refresh_serial_ports(auto_connect=True)
        self.textedit.setFocus()
        self.last_ports = set(list_serial_ports())
        self.port_monitor_timer = QTimer(self)
        self.port_monitor_timer.timeout.connect(self.check_ports_changed)
        self.port_monitor_timer.start(1000)

    def closeEvent(self, event):
        if self.selected_port:
            self.save_recent_port(self.selected_port)
        if self.serial and self.serial.is_open:
            self.serial.close()
        event.accept()

    def load_recent_ports(self):
        try:
            with open(USER_PORT_LIST, "r", encoding="utf-8") as f:
                ports = json.load(f)
                # index migration 및 정렬
                migrated = False
                for idx, entry in enumerate(ports):
                    if 'index' not in entry:
                        entry['index'] = idx
                        migrated = True
                ports.sort(key=lambda x: x.get('index', 0))
                for i, entry in enumerate(ports):
                    entry['index'] = i
                if migrated:
                    with open(USER_PORT_LIST, "w", encoding="utf-8") as fw:
                        json.dump(ports, fw, indent=2)
                return ports
        except Exception:
            return []

    def save_recent_port(self, port):
        ports = self.load_recent_ports()
        # Remove if already exists
        ports = [p for p in ports if p['settings'].get('port') != port]
        settings = {
            "port": port,
            "baudrate": self.baudrate,
            "parity": getattr(self, "parity", "N"),
            "stopbits": getattr(self, "stopbits", 1),
            "bytesize": getattr(self, "bytesize", 8),
            "timeout": getattr(self, "timeout", 0.1)
        }
        ports = [{"settings": settings, "index": 0}] + [
            {"settings": p["settings"], "index": i+1} for i, p in enumerate(ports[:4])
        ]
        for i, entry in enumerate(ports):
            entry['index'] = i
        try:
            with open(USER_PORT_LIST, "w", encoding="utf-8") as f:
                json.dump(ports, f, indent=2)
        except Exception:
            pass

    def update_status_bar(self, message):
        self.status.showMessage(message)

    def show_about_dialog(self):
        QMessageBox.about(self, "About AT Commander", "AT Command Terminal Emulator\n\nVersion 0.7\n\nBy OllehEugene with AI")

    def apply_theme(self, theme_name):
        if theme_name == "default":
            QApplication.instance().setStyleSheet("")
        else:
            theme_path = get_resources(theme_name)
            if os.path.exists(theme_path):
                with open(theme_path, "r") as f:
                    style = f.read()
                    QApplication.instance().setStyleSheet(style)

    def on_port_changed(self, port):
        self.selected_port = port
        if self.serial and self.serial.is_open:
            self.serial.close()
            self.connect_btn.setChecked(False)
            self.connect_btn.setText("Connect")
            self.toggle_serial_connection()

    def on_baudrate_changed(self, baudrate):
        self.baudrate = int(baudrate)

    def toggle_serial_connection(self):
        if self.serial and self.serial.is_open:
            self.serial.close()
            self.update_status_bar("Disconnected")
            self.connect_btn.setChecked(False)
            self.connect_btn.setText("Connect")
        else:
            try:
                self.serial = serial.Serial(self.selected_port, self.baudrate, timeout=1)
                self.update_status_bar(f"Connected to {self.selected_port} at {self.baudrate} baud")
                self.connect_btn.setChecked(True)
                self.connect_btn.setText("Disconnect")
                self.save_recent_port(self.selected_port)
            except serial.SerialException as e:
                QMessageBox.critical(self, "Connection Error", str(e))

    def refresh_serial_ports(self, auto_connect=False):
        current_port = self.serial_port_combo.currentText()
        ports = list_serial_ports()
        self.serial_port_combo.clear()
        self.serial_port_combo.addItems(ports)

        if auto_connect:
            for entry in self.recent_ports:
                port_candidate = entry["settings"].get("port", "").strip()
                if port_candidate and port_candidate in ports:
                    self.serial_port_combo.setCurrentText(port_candidate)
                    self.selected_port = port_candidate
                    self.toggle_serial_connection()
                    break
            else:
                if ports:
                    self.serial_port_combo.setCurrentIndex(0)
                    self.selected_port = ports[0]
        else:
            if current_port in ports:
                self.serial_port_combo.setCurrentText(current_port)
                self.selected_port = current_port
            elif ports:
                self.serial_port_combo.setCurrentIndex(0)
                self.selected_port = ports[0]

    def clear_terminal(self):
        self.textedit.clear()

    def toggle_left_panel(self):
        if self.left_panel_visible:
            self.splitter.setSizes([0, 24, 850])
            self.toggle_btn.setIcon(QIcon(get_resources("right-3arrow.png")))
        else:
            self.splitter.setSizes([250, 24, 850])
            self.toggle_btn.setIcon(QIcon(get_resources("left-3arrow.png")))
        self.left_panel_visible = not self.left_panel_visible

    def send_lineedit_command(self, index):
        command = self.lineedits[index].text()
        if command and self.serial and self.serial.is_open:
            self.serial.write((command + "\r").encode())
            self.lineedits[index].clear()

    def save_checkbox_lineedit_to_json(self, filename):
        data = []
        old_map = {}
        try:
            with open(filename, "r", encoding="utf-8") as f:
                old_data = json.load(f)
            if isinstance(old_data, list):
                for item in old_data:
                    idx = item.get("index")
                    if idx is not None:
                        old_map[idx] = {
                            "time": item.get("time", 0.5),
                            "disabled": item.get("title", {}).get("disabled", False)
                        }
        except Exception:
            pass
        for i in range(10):
            checkbox = self.checkboxes[i]
            lineedit = self.lineedits[i]
            prev = old_map.get(i, {})
            item = {
                "index": i,
                "checked": checkbox.isChecked(),
                "title": {
                    "text": lineedit.text(),
                    "disabled": prev.get("disabled", False)
                },
                "time": prev.get("time", 0.5)
            }
            data.append(item)
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def load_checkbox_lineedit_from_json(self, filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 리스트 구조 (신규/정상)
                if isinstance(data, list):
                    for item in data:
                        idx = item.get("index")
                        if idx is not None and 0 <= idx < len(self.checkboxes):
                            checked = bool(item.get("checked", False))
                            text = item.get("title", {}).get("text", "")
                            disabled = item.get("title", {}).get("disabled", False)
                            self.checkboxes[idx].setChecked(checked)
                            self.lineedits[idx].setText(text)
                            self.checkboxes[idx].setDisabled(disabled)
                            self.lineedits[idx].setDisabled(disabled)
                            self.sendline_btns[idx].setDisabled(disabled)
                            self.checkboxes[idx].setVisible(not disabled)
                            self.sendline_btns[idx].setVisible(not disabled)
                            self.lineedits[idx].setVisible(True)
                            if disabled:
                                self.lineedits[idx].setAlignment(Qt.AlignCenter)
                            else:
                                self.lineedits[idx].setAlignment(Qt.AlignLeft)
                elif isinstance(data, dict):
                    for i in range(10):
                        checkbox = self.checkboxes[i]
                        lineedit = self.lineedits[i]
                        send_btn = self.sendline_btns[i]
                        command_key = f"command_{i+1}"
                        if command_key in data:
                            lineedit.setText(data[command_key])
                            checkbox.setChecked(True)
                            checkbox.setDisabled(False)
                            lineedit.setDisabled(False)
                            send_btn.setDisabled(False)
                            checkbox.setVisible(True)
                            lineedit.setVisible(True)
                            send_btn.setVisible(True)
                            lineedit.setAlignment(Qt.AlignLeft)
                        else:
                            lineedit.clear()
                            checkbox.setChecked(False)
                            checkbox.setDisabled(False)
                            lineedit.setDisabled(False)
                            send_btn.setDisabled(False)
                            checkbox.setVisible(True)
                            lineedit.setVisible(True)
                            send_btn.setVisible(True)
                            lineedit.setAlignment(Qt.AlignLeft)
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def update_terminal(self, data):
        cursor = self.textedit.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(data)
        self.textedit.setTextCursor(cursor)
        self.textedit.ensureCursorVisible()

    def sequential_send_commands(self):
        if self.serial and self.serial.is_open:
            for i in range(10):
                lineedit = self.lineedits[i]
                if lineedit.text():
                    self.serial.write((lineedit.text() + "\r").encode())
                    time.sleep(0.1)

    def check_ports_changed(self):
        current_ports = set(list_serial_ports())
        if current_ports != self.last_ports:
            self.refresh_serial_ports()
            self.last_ports = current_ports
