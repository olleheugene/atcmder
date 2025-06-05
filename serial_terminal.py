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
from utils import get_resources, expand_ansi_tabs, expand_ansi_cursor_right, process_ansi_spacing,USER_COMMAND_LIST, USER_PORT_LIST

# Helper for serial port listing
import serial.tools.list_ports
def list_serial_ports():
    return [port.device for port in serial.tools.list_ports.comports()]

class SerialTerminal(QMainWindow):
    serial_data_signal = Signal(str)
    sequential_complete_signal = Signal(bool, str)  # success flag, message

    def __init__(self, port=None, baudrate=115200):
        super().__init__()
        self.setWindowTitle("AT Commander v0.7")
        self.resize(1100, 600)
        program_icon_path = get_resources("app_icon.png")
        self.data_buffer = ""
        self.buffer_timeout = None
        self.ansi_buffer = ""  # Buffer for incomplete ANSI sequences
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
            
            # Create a proper closure for the button click
            def make_send_handler(index):
                return lambda: self.send_lineedit_command(index)
            
            send_btn.clicked.connect(make_send_handler(i))
            checkbox.stateChanged.connect(lambda state, idx=i: self.save_checkbox_lineedit_to_json(USER_COMMAND_LIST))
            lineedit.textChanged.connect(lambda text, idx=i: self.save_checkbox_lineedit_to_json(USER_COMMAND_LIST))
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
        self.clear_btn.setToolTip("Clear terminal window")
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
        self.sequential_complete_signal.connect(self.on_sequential_complete)
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
        self.port_monitor_timer.start(1000)  # Check for port changes every 1 second

    def eventFilter(self, obj, event):
        if obj is self.textedit:
            # Handle mouse click events - always move cursor to end
            if event.type() == QEvent.MouseButtonPress:
                # Move cursor to end on any mouse click
                self.textedit.moveCursor(QTextCursor.End)
                return False  # Allow normal mouse event processing
            
            # Handle key press events
            elif event.type() == QEvent.KeyPress:
                key = event.key()
                text = event.text()
                
                # Always move cursor to end for any key input
                self.textedit.moveCursor(QTextCursor.End)

                if self.serial and self.serial.is_open:
                    if key == Qt.Key_Return or key == Qt.Key_Enter:
                        # Send \r\n when Enter key is pressed (can be changed to \r or \n as needed)
                        command_to_send = self.current_input_buffer + "\r\n" 
                        self.serial.write(command_to_send.encode('utf-8', errors='replace'))
                        
                        # Add current input to history
                        if self.current_input_buffer:
                            if self.current_input_buffer in self.command_history:
                                self.command_history.remove(self.current_input_buffer)
                            self.command_history.insert(0, self.current_input_buffer)
                            if len(self.command_history) > 50:  # Maximum 50 history entries
                                self.command_history.pop()
                        
                        self.current_input_buffer = ""  # Clear input buffer
                        self.history_index = -1  # Reset history index
                        # self.textedit.moveCursor(QTextCursor.End)  # Don't move cursor here, wait for echo
                        # self.textedit.insertPlainText("\n")  # Use for local echo if needed, usually device echoes
                        return True  # Event handling complete
                    
                    elif key == Qt.Key_Up:
                        # Move to previous command in history
                        if self.command_history and self.history_index < len(self.command_history) - 1:
                            self.history_index += 1
                            historic_command = self.command_history[self.history_index]
                            
                            # Replace current input buffer with history command
                            self.current_input_buffer = historic_command
                            
                            # Replace current line input in text editor
                            cursor = self.textedit.textCursor()
                            cursor.movePosition(QTextCursor.End)
                            cursor.movePosition(QTextCursor.StartOfLine, QTextCursor.KeepAnchor)
                            cursor.removeSelectedText()
                            cursor.insertText(historic_command)
                        return True

                    elif key == Qt.Key_Down:
                        # Move to next command in history (more recent direction)
                        if self.history_index > 0:
                            self.history_index -= 1
                            historic_command = self.command_history[self.history_index]
                            
                            # Replace current input buffer with history command
                            self.current_input_buffer = historic_command
                            
                            # Replace current line input in text editor
                            cursor = self.textedit.textCursor()
                            cursor.movePosition(QTextCursor.End)
                            cursor.movePosition(QTextCursor.StartOfLine, QTextCursor.KeepAnchor)
                            cursor.removeSelectedText()
                            cursor.insertText(historic_command)
                        elif self.history_index == 0:
                            # When at most recent (first) command in history, down key goes to empty line
                            self.history_index = -1
                            self.current_input_buffer = ""
                            
                            cursor = self.textedit.textCursor()
                            cursor.movePosition(QTextCursor.End)
                            cursor.movePosition(QTextCursor.StartOfLine, QTextCursor.KeepAnchor)
                            cursor.removeSelectedText()
                        return True
                    
                    elif key == Qt.Key_Backspace:
                        if self.current_input_buffer:
                            self.current_input_buffer = self.current_input_buffer[:-1]
                        return False  # Allow QTextEdit's default behavior (delete character)

                    elif text and (text.isprintable() or key == Qt.Key_Space):
                        self.current_input_buffer += text
                        return False  # Allow QTextEdit's default behavior (insert character)
                    
                    elif key == Qt.Key_Tab:
                        # Tab key handling - send tab character (\t)
                        self.serial.write(b'\t')
                        # self.current_input_buffer += '\t'
                        # # Display tab as spaces in QTextEdit (8 spaces)
                        # cursor = self.textedit.textCursor()
                        # cursor.insertText('        ')  # Display as 8 spaces
                        return True  # Event handling complete
                    
                    # Send special keys like Ctrl+C (if needed)
                    # elif event.modifiers() == Qt.ControlModifier and key == Qt.Key_C:
                    #     self.serial.write(b'\x03')  # Ctrl+C (ETX)
                    #     return True

                    return False  # Default handling for other keys
                else:  # When serial is not connected
                    # ... (existing logic: newline on enter, etc.) ...
                    if key == Qt.Key_Return or key == Qt.Key_Enter:
                        self.current_input_buffer = ""  # Clear input buffer
                        return False  # Normal QTextEdit enter behavior
                    elif text and (text.isprintable() or key == Qt.Key_Space):
                        self.current_input_buffer += text
                        return False
                    elif key == Qt.Key_Backspace:
                        if self.current_input_buffer:
                            self.current_input_buffer = self.current_input_buffer[:-1]
                        return False
        return super().eventFilter(obj, event)

    def save_recent_ports(self):
        # Save recent port list
        try:
            with open(USER_PORT_LIST, "w", encoding="utf-8") as f:
                json.dump(self.recent_ports, f, indent=2)
        except Exception:
            pass

    def closeEvent(self, event):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=0.5)
        self.save_recent_ports()
        if self.serial and self.serial.is_open:
            self.serial.close()
        event.accept()

    def load_recent_ports(self):
        # Load recent port list from USER_PORT_LIST
        try:
            with open(USER_PORT_LIST, "r", encoding="utf-8") as f:
                ports = json.load(f)
                # Index migration and sorting
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
        # Save to recent port list on successful connection (remove duplicates, keep 5, reorder index)
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
        # If connected, disconnect and reconnect to new port
        if self.serial and self.serial.is_open:
            self.serial.close()
            self.connect_btn.setChecked(False)
            self.connect_btn.setText("Connect")
            # Immediately reconnect
            self.toggle_serial_connection()

    def on_baudrate_changed(self, baudrate):
        self.baudrate = int(baudrate)

    def toggle_serial_connection(self):
        if self.serial and self.serial.is_open:
            self.running = False
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=0.5)
            self.serial.close()
            self.update_status_bar("Disconnected")
            self.connect_btn.setChecked(False)
            self.connect_btn.setText("Connect")
        else:
            try:
                self.serial = serial.Serial(self.selected_port, self.baudrate, timeout=0.1)
                self.running = True
                self.thread = threading.Thread(target=self.read_serial_data, daemon=True)
                self.thread.start()
                self.update_status_bar(f"Connected to {self.selected_port} at {self.baudrate} bps")
                self.connect_btn.setChecked(True)
                self.connect_btn.setText("Disconnect")
                self.save_recent_port(self.selected_port)  # Save recent port
            except serial.SerialException as e:
                QMessageBox.critical(self, "Connection Error", str(e))

    def refresh_serial_ports(self, auto_connect=False):
        current_port = self.serial_port_combo.currentText()
        if self.serial and self.serial.is_open:
            self.serial.close()
            self.connect_btn.setChecked(False)
            self.connect_btn.setText("Connect")
        ports = list_serial_ports()
        self.serial_port_combo.clear()
        self.serial_port_combo.addItems(ports)

        if auto_connect:
            # Auto-connect to available ports in order of recent port list index
            for entry in self.recent_ports:
                port_candidate = entry["settings"].get("port", "").strip()
                if port_candidate and port_candidate in ports:
                    self.serial_port_combo.setCurrentText(port_candidate)
                    self.selected_port = port_candidate
                    self.toggle_serial_connection()
                    break
            else:
                # If none available, use first port
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
            try:
                # Add command to history
                if command not in self.command_history:
                    self.command_history.insert(0, command)
                    if len(self.command_history) > 50:
                        self.command_history.pop()
                
                # Send command with carriage return and line feed
                command_bytes = (command + "\r\n").encode('utf-8', errors='replace')
                bytes_written = self.serial.write(command_bytes)
                
                # Update status bar with success message
                # self.update_status_bar(f"Sent: {command}")
                
                # Display sent command in terminal for verification
                self.serial_data_signal.emit(f"> {command}")
                
            except Exception as e:
                # Handle encoding or serial errors
                self.update_status_bar(f"Send error: {str(e)}")
        elif not self.serial or not self.serial.is_open:
            self.update_status_bar("Error: Not connected to serial port")
        elif not command:
            self.update_status_bar("Error: No command to send")

    def save_checkbox_lineedit_to_json(self, filename):
        data = []
        # Read JSON first to preserve existing time/disabled values
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
                # List structure (new/normal)
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
                            # If disabled, hide checkbox/button only, lineedit always visible
                            self.checkboxes[idx].setVisible(not disabled)
                            self.sendline_btns[idx].setVisible(not disabled)
                            self.lineedits[idx].setVisible(True)
                            # Apply alignment dynamically
                            if disabled:
                                self.lineedits[idx].setAlignment(Qt.AlignCenter)
                            else:
                                self.lineedits[idx].setAlignment(Qt.AlignLeft)
                # Dictionary structure (old/temporary)
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
        """Output serial data to terminal (including ANSI processing)"""
        # Use ANSI processing functions from utils.py (process_ansi_spacing includes all space handling)
        data = process_ansi_spacing(data)
        
        cursor = self.textedit.textCursor()
        is_at_end = cursor.atEnd()
        
        # Move cursor to end
        self.textedit.moveCursor(QTextCursor.End)
        
        try:
            # ANSI to HTML conversion to maintain colors
            html_output = self.ansi_conv.convert(data, full=False)
            if html_output.strip():
                # Handle line breaks properly in HTML
                # Manual processing in case ansi2html doesn't convert line breaks to <br>
                html_output = html_output.replace('\n', '<br>')
                # Convert consecutive spaces to &nbsp; to prevent HTML from collapsing spaces
                import re
                html_output = re.sub(r'  +', lambda m: '&nbsp;' * len(m.group()), html_output)
                self.textedit.insertHtml(html_output)
        except Exception:
            # Fallback to plain text on ANSI conversion failure
            if data.strip():
                self.textedit.insertPlainText(data)
        
        # Auto-scroll if user was viewing the end
        if is_at_end:
            self.textedit.ensureCursorVisible()
        
        # Always ensure cursor is at the end for user input
        self.textedit.moveCursor(QTextCursor.End)

    def read_serial_data(self):
        """Thread function to read serial data"""
        buffer_start_time = None
        
        while self.running and self.serial and self.serial.is_open:
            try:
                if self.serial.in_waiting > 0:
                    data_bytes = self.serial.read(self.serial.in_waiting)
                    try:
                        # Try UTF-8 decoding
                        data_str = data_bytes.decode('utf-8', errors='replace')
                    except UnicodeDecodeError:
                        # Fall back to latin-1 if UTF-8 fails
                        data_str = data_bytes.decode('latin-1', errors='replace')
                    
                    if data_str:
                        # Combine with any buffered incomplete ANSI sequence
                        combined_data = self.ansi_buffer + data_str
                        
                        # Check if ANSI sequences are complete
                        is_complete, incomplete_pos = self.is_ansi_sequence_complete(combined_data)
                        
                        if is_complete:
                            # All sequences are complete, emit the data
                            self.ansi_buffer = ""
                            buffer_start_time = None
                            self.serial_data_signal.emit(combined_data)
                        else:
                            # Incomplete sequence found, buffer the incomplete part
                            complete_part = combined_data[:incomplete_pos]
                            incomplete_part = combined_data[incomplete_pos:]
                            
                            # Emit the complete part if it exists
                            if complete_part:
                                self.serial_data_signal.emit(complete_part)
                            
                            # Buffer the incomplete part
                            self.ansi_buffer = incomplete_part
                            
                            # Set buffer start time for timeout
                            if buffer_start_time is None:
                                buffer_start_time = time.time()
                else:
                    # Check for buffer timeout (100ms)
                    if self.ansi_buffer and buffer_start_time is not None:
                        if time.time() - buffer_start_time > 0.1:  # 100ms timeout
                            # Flush the buffer
                            self.serial_data_signal.emit(self.ansi_buffer)
                            self.ansi_buffer = ""
                            buffer_start_time = None
                            
            except serial.SerialException:
                # Disconnect on serial port error
                self.running = False
                QTimer.singleShot(0, lambda: self.update_status_bar("Port error. Disconnected."))
                QTimer.singleShot(0, lambda: self.connect_btn.setChecked(False))
                QTimer.singleShot(0, lambda: self.connect_btn.setText("Connect"))
                if self.serial and self.serial.is_open:
                    try:
                        self.serial.close()
                    except:
                        pass
                self.serial = None
                break
            except Exception:
                self.running = False
                break
            time.sleep(0.01)  # Reduce CPU usage

    def sequential_send_commands(self):
        if self.serial and self.serial.is_open:
            # Collect all commands to send with their time intervals
            commands_to_send = []
            
            # Load time intervals from JSON file
            time_intervals = {}
            try:
                with open(USER_COMMAND_LIST, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        idx = item.get("index")
                        if idx is not None:
                            time_intervals[idx] = item.get("time", 1.0)  # Default 1 second
            except Exception:
                pass
            
            for i in range(10):
                lineedit = self.lineedits[i]
                checkbox = self.checkboxes[i]
                if lineedit.text() and checkbox.isChecked():
                    time_interval = time_intervals.get(i, 1.0)  # Default 1 second if not found
                    commands_to_send.append((i, lineedit.text(), time_interval))
            
            if commands_to_send:
                # Disable the sequential button during execution
                self.sequential_btn.setEnabled(False)
                self.sequential_btn.setText("Sending...")
                
                # Start sequential sending in a separate thread
                import threading
                def send_commands_thread():
                    success = True
                    error_msg = ""
                    
                    try:
                        for idx, (i, command, time_interval) in enumerate(commands_to_send):
                            if not self.serial or not self.serial.is_open:
                                success = False
                                error_msg = "Serial connection lost"
                                break
                                
                            try:
                                command_bytes = (command + "\r\n").encode('utf-8', errors='replace')
                                bytes_written = self.serial.write(command_bytes)
                                
                                # Update status bar with success message including time interval
                                def update_status(cmd, num, total, interval):
                                    self.update_status_bar(f"Sequential Send [{num}/{total}]: {cmd} (delay: {interval}s)")
                                
                                QTimer.singleShot(0, lambda cmd=command, num=idx+1, total=len(commands_to_send), interval=time_interval: update_status(cmd, num, total, interval))
                                
                                # Display sent command in terminal for verification
                                self.serial_data_signal.emit(f"> {command}\n")
                                
                                # Add to history
                                if command not in self.command_history:
                                    self.command_history.insert(0, command)
                                    if len(self.command_history) > 50:
                                        self.command_history.pop()
                                
                                # Wait for the specified time interval before sending next command
                                time.sleep(time_interval)
                                
                            except Exception as e:
                                def update_error(err):
                                    self.update_status_bar(f"Sequential send error: {err}")
                                    
                                QTimer.singleShot(0, lambda err=str(e): update_error(err))
                                success = False
                                error_msg = str(e)
                                break
                                
                    except Exception as e:
                        success = False
                        error_msg = str(e)
                    
                    finally:
                        # Always restore button state regardless of success or failure
                        if success:
                            self.sequential_complete_signal.emit(True, "Sequential send completed")
                        else:
                            self.sequential_complete_signal.emit(False, f"Sequential send failed: {error_msg}")
                
                thread = threading.Thread(target=send_commands_thread, daemon=True)
                thread.start()
            else:
                self.update_status_bar("No commands selected for sequential send")
        else:
            self.update_status_bar("Not connected to serial port")

    def on_sequential_complete(self, success, message):
        """Handle sequential send completion in the main thread"""
        self.sequential_btn.setEnabled(True)
        self.sequential_btn.setText("Sequential Send")
        self.update_status_bar(message)

    def check_ports_changed(self):
        current_ports = set(list_serial_ports())
        if current_ports != self.last_ports:
            self.refresh_serial_ports()
            self.last_ports = current_ports

    def is_ansi_sequence_complete(self, data):
        """Check if all ANSI escape sequences in data are complete"""
        # Enhanced ANSI pattern that covers color codes, cursor movement, and other sequences
        # Final characters include: letters (a-zA-Z), digits in some cases, and special chars like @, ~, etc.
        ansi_pattern = re.compile(r'\x1b\[[0-9;:<=>?]*[a-zA-Z@~]')
        
        # Find all potential ANSI sequence starts
        i = 0
        while i < len(data):
            if data[i] == '\x1b':
                if i + 1 < len(data) and data[i + 1] == '[':
                    # This is an ANSI CSI sequence, check if it's complete
                    remaining = data[i:]
                    match = ansi_pattern.match(remaining)
                    if not match:
                        # Incomplete sequence found
                        return False, i
                    # Move past this complete sequence
                    i += match.end()
                else:
                    # Incomplete escape sequence (just \x1b without [)
                    if i + 1 >= len(data):
                        return False, i
                    i += 1
            else:
                i += 1
        
        return True, -1
