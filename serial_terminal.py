import os
import serial
import threading
import time
import re
import subprocess
from PySide6.QtWidgets import (
    QMainWindow, QLineEdit, QPushButton, QVBoxLayout, QWidget, QHBoxLayout, QCheckBox, QComboBox, QLabel, QGroupBox, QSizePolicy, QMessageBox, QSplitter, QApplication, QFileDialog, QDialog
)
from PySide6.QtGui import QIcon, QFont, QAction, QGuiApplication
from PySide6.QtCore import Signal, Qt, QEvent, QTimer
import utils
from terminal_widget import TerminalWidget
from yaml_editor import YamlEditorDialog
import yaml

LINEEDIT_MAX_NUMBER = 10  # Maximum number of line edits

import serial.tools.list_ports
def list_serial_ports():
    return [port.device for port in serial.tools.list_ports.comports()]

class SerialTerminal(QMainWindow):
    serial_data_signal = Signal(str)
    sequential_complete_signal = Signal(bool, str)
    reconnect_signal = Signal()

    @staticmethod
    def clear_layout(layout):
        if layout is not None:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget() is not None:
                    child.widget().deleteLater()
                elif child.layout() is not None:
                    SerialTerminal.clear_layout(child.layout())

    def __init__(self, port=None, baudrate=115200):
        super().__init__()
        utils.prepare_default_files()
        self.setWindowTitle("AT Commander v" + utils.APP_VERSION)
        self.resize(1100, 600)
        self.serial = None
        self.running = False
        self.thread = None
        self.command_history = []
        self.history_index = -1
        self.current_input_buffer = ""

        self._status_timer = QTimer()
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self._restore_connection_status)

        self.load_command_history()
        program_icon_path = utils.get_resources(utils.APP_ICON_NAME)
        if os.path.exists(program_icon_path):
            self.setWindowIcon(QIcon(program_icon_path))
        self.first_load = True
        self.data_buffer = ""
        self.buffer_timeout = None
        self.ansi_buffer = ""
        self.current_cmdlist_file = None
        self.full_command_list = []
        self.current_page = 0
        self.font_size = self.load_font_settings().get("size", 14)
        self.font_family = self.load_font_settings().get("family", "Monaco")
        self.auto_scroll_enabled = True
        self.comport_settings = []
        self.recent_ports = self.load_recent_ports()
        self.selected_port = port or ""
        self.baudrate = baudrate
        self.status = self.statusBar()
        self.update_status_bar("Disconnected")
        self.author_label = QLabel("By OllehEugene")
        self.author_label.setStyleSheet("color: #888; margin-left: 12px;")
        self.status.addPermanentWidget(self.author_label)

        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        load_commands_action = QAction("Load CMD list", self)
        load_commands_action.triggered.connect(self.load_command_list_from_file)
        file_menu.addAction(load_commands_action)
        edit_cmd_action = QAction("Edit CMD list", self)
        edit_cmd_action.setToolTip("Edit the currently selected predefined command list in your default editor")
        edit_cmd_action.triggered.connect(self.edit_current_command_list)
        file_menu.addAction(edit_cmd_action)
        open_config_folder_action = QAction("Open Configfile folder", self)
        open_config_folder_action.triggered.connect(self.open_config_folder)
        file_menu.addAction(open_config_folder_action)
        file_menu.addSeparator()
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        help_menu = menubar.addMenu("Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)
        view_menu = menubar.addMenu("View")
        increase_font_action = QAction("Increase Font Size", self)
        increase_font_action.setShortcut("Ctrl++")
        increase_font_action.triggered.connect(self.increase_font_size)
        view_menu.addAction(increase_font_action)
        decrease_font_action = QAction("Decrease Font Size", self)
        decrease_font_action.setShortcut("Ctrl+-")
        decrease_font_action.triggered.connect(self.decrease_font_size)
        view_menu.addAction(decrease_font_action)
        reset_font_action = QAction("Reset Font Size", self)
        reset_font_action.setShortcut("Ctrl+0")
        reset_font_action.triggered.connect(self.reset_font_size)
        view_menu.addAction(reset_font_action)
        view_menu.addSeparator()
        self.reconnect_signal.connect(self.try_reconnect_serial)
        self.font_size_action = QAction(f"Current Font Size: {self.font_size}", self)
        self.font_size_action.setEnabled(False)
        view_menu.addAction(self.font_size_action)
        view_menu.addSeparator()
        theme_menu = menubar.addMenu("Theme")
        light_action = QAction("Light", self)
        dark_action = QAction("Dark", self)
        default_action = QAction("Default", self)
        light_action.triggered.connect(lambda: self.apply_theme(utils.LIGHT_CSS_NAME))
        dark_action.triggered.connect(lambda: self.apply_theme(utils.DARK_CSS_NAME))
        default_action.triggered.connect(lambda: self.apply_theme(utils.DEFAULT_CSS_NAME))
        theme_menu.addAction(light_action)
        theme_menu.addAction(dark_action)
        theme_menu.addAction(default_action)
        self.apply_theme(self.load_theme_settings())

        self.left_widget = QWidget()
        self.left_layout = QVBoxLayout()
        self.left_layout.setSpacing(3) 
        self.serial_group = QGroupBox("Serial Settings")
        serial_group_layout = QVBoxLayout()
        serial_group_layout.setSpacing(0)
        serial_group_layout.setContentsMargins(0, 0, 0, 0)

        self.serial_port_combo = QComboBox()
        self.serial_port_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        port_layout = QHBoxLayout()
        port_layout.setSpacing(0)
        port_layout.setContentsMargins(0, 0, 0, 0)
        self.port_label = QLabel("Port:")
        self.port_label.setContentsMargins(5, 0, 5, 0)
        port_layout.addWidget(self.port_label)
        port_layout.addWidget(self.serial_port_combo)
        serial_group_layout.addLayout(port_layout)

        self.serial_port_combo.currentTextChanged.connect(self.on_port_changed)
        baud_btn_layout = QHBoxLayout()
        baud_btn_layout.setSpacing(0)
        baud_btn_layout.setContentsMargins(10, 0, 10, 0)
        self.baudrate_combo = QComboBox()
        baudrates = ["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600", "1000000"]
        self.baudrate_combo.addItems(baudrates)
        self.baudrate_combo.setCurrentText(str(self.baudrate))
        self.baudrate_combo.setEditable(True)
        from PySide6.QtGui import QIntValidator
        self.baudrate_combo.lineEdit().setValidator(QIntValidator(1, 10000000, self))
        self.baudrate_combo.currentTextChanged.connect(self.on_baudrate_changed)
        self.baudrate_combo.setContentsMargins(0, 0, 20, 0)
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setCheckable(True)
        self.connect_btn.clicked.connect(self.toggle_serial_connection)
        self.connect_btn.setFixedWidth(90) 
        self.connect_btn.setToolTip(f"Connect to selected port")
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_serial_ports)
        self.refresh_btn.setFixedWidth(70) 
        self.baud_label = QLabel("Baudrate:")
        baud_btn_layout.addWidget(self.baud_label)
        baud_btn_layout.addWidget(self.baudrate_combo)
        baud_btn_layout.addWidget(self.connect_btn)
        baud_btn_layout.addWidget(self.refresh_btn)
        baud_btn_layout.setContentsMargins(5, 0, 5, 0)
        serial_group_layout.addLayout(baud_btn_layout)
        self.serial_group.setLayout(serial_group_layout)
        self.left_layout.addWidget(self.serial_group)

        # --- Add pagination group ---
        self.pagination_group = QGroupBox("Command Pages")
        self.pagination_layout = QHBoxLayout()
        self.pagination_group.setLayout(self.pagination_layout)
        self.left_layout.addWidget(self.pagination_group)
        self.pagination_group.hide()
        # --- End of added button group ---

        self.checkboxes = []
        self.lineedits = []
        self.sendline_btns = []
        for i in range(LINEEDIT_MAX_NUMBER):
            row_widget = QWidget()
            row_layout = QHBoxLayout()
            checkbox = QCheckBox()
            lineedit = QLineEdit()
            send_btn = QPushButton("Send")
            send_btn.setToolTip(f"Send command to serial port")
            def make_send_handler(index):
                return lambda: self.send_lineedit_command(index)
            send_btn.clicked.connect(make_send_handler(i))
            checkbox.stateChanged.connect(lambda state, idx=i: self.save_checkbox_lineedit())
            lineedit.textChanged.connect(lambda text, idx=i: self.save_checkbox_lineedit())
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
        self.terminal_widget = TerminalWidget(font_family=self.font_family, font_size=self.font_size)
        self.terminal_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.terminal_widget.installEventFilter(self)
        self.clear_btn = QPushButton()
        self.clear_btn.setIcon(QIcon(utils.get_resources(utils.CLEAR_ICON_NAME)))
        self.clear_btn.setFixedSize(24, 24)
        self.clear_btn.setToolTip("Clear terminal window")
        self.clear_btn.clicked.connect(self.clear_terminal)
        self.right_layout = QVBoxLayout()
        self.top_right_btn_layout = QHBoxLayout()
        self.top_right_btn_layout.addStretch()
        self.top_right_btn_layout.addWidget(self.clear_btn)
        btn_v_layout = QVBoxLayout()
        btn_v_layout.addSpacing(10)
        btn_v_layout.addLayout(self.top_right_btn_layout)
        self.right_layout.addLayout(btn_v_layout)
        self.right_layout.addWidget(self.terminal_widget)
        self.right_widget = QWidget()
        self.right_widget.setLayout(self.right_layout)
        self.toggle_btn = QPushButton()
        self.toggle_btn.setFixedWidth(24)
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setToolTip("Expand/Collapse the terminal window")
        self.toggle_btn.setIcon(QIcon(utils.get_resources(utils.LEFT_ARROW_ICON_NAME)))
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
        splitter.addWidget(self.right_widget)
        splitter.setSizes([250, 24, 850])
        central = QWidget()
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(splitter)
        central.setLayout(main_layout)
        self.setCentralWidget(central)
        self.splitter = splitter
        self.left_panel_visible = True
        self.serial_data_signal.connect(self.update_terminal)
        self.sequential_complete_signal.connect(self.on_sequential_complete)
        # Set default YAML file as current
        self.current_cmdlist_file = utils.USER_COMMAND_LIST
        self.load_checkbox_lineedit(self.current_cmdlist_file)
        self.sequential_btn = QPushButton("Sequential Send")
        self.sequential_btn.clicked.connect(self.sequential_send_commands)
        self.left_layout.addWidget(self.sequential_btn)
        self.refresh_serial_ports(auto_connect=True)
        self.terminal_widget.setFocus()
        self.auto_load_selected_commandlist_file()
        self.update_config_file_status()
        self.last_ports = set(list_serial_ports())
        self._display_buffer = ""

    def eventFilter(self, obj, event):
        key = None
        text = ""
        if obj is self.terminal_widget:
            if event.type() == QEvent.Type.Resize:
                return False  # Let Qt handle resizing
            if event.type() == QEvent.Type.KeyPress:
                key = event.key()
                text = event.text()
                modifiers = event.modifiers()

                # Font size adjustment
                if modifiers == Qt.KeyboardModifier.ControlModifier:
                    # Ctrl + Plus
                    if key == Qt.Key.Key_Plus or key == Qt.Key.Key_Equal:
                        self.increase_font_size()
                        return True
                    elif key == Qt.Key.Key_Minus:
                        self.decrease_font_size()
                        return True
                    elif key == Qt.Key.Key_0:
                        self.reset_font_size()
                        return True
                    elif key == Qt.Key.Key_C:
                        self.handle_ctrl_c()
                        return True
                    elif key == Qt.Key.Key_V:
                        self.handle_paste()
                        return True
                elif modifiers == Qt.KeyboardModifier.AltModifier:
                    # Alt + 1
                    if key == Qt.Key.Key_1:
                        self.send_lineedit_command(1)
                        return True
                    elif key == Qt.Key.Key_2:
                        self.send_lineedit_command(2)
                        return True
                    elif key == Qt.Key.Key_3:
                        self.send_lineedit_command(3)
                        return True
                    elif key == Qt.Key.Key_4:
                        self.send_lineedit_command(4)
                        return True
                    elif key == Qt.Key.Key_5:
                        self.send_lineedit_command(5)
                        return True
                    elif key == Qt.Key.Key_6:
                        self.send_lineedit_command(6)
                        return True
                    elif key == Qt.Key.Key_7:
                        self.send_lineedit_command(7)
                        return True
                    elif key == Qt.Key.Key_8:
                        self.send_lineedit_command(8)
                        return True
                    elif key == Qt.Key.Key_9:
                        self.send_lineedit_command(9)
                        return True
                    elif key == Qt.Key.Key_0:
                        self.send_lineedit_command(0)
                        return True
                else:
                    if key == Qt.Key_F1:
                        self.show_shortcut_list()
                        return True
                    elif key == Qt.Key_F2:
                        # Connect if not already connected
                        if not (self.serial and self.serial.is_open):
                            self.toggle_serial_connection()
                        return True
                    elif key == Qt.Key_F3:
                        # Disconnect if connected
                        if self.serial and self.serial.is_open:
                            self.toggle_serial_connection()
                        return True
                    elif key == Qt.Key_F4:
                        self.serial_port_combo.showPopup()
                        return True
                    elif key == Qt.Key_F5:
                        self.refresh_serial_ports(False)
                        return True
                    elif key == Qt.Key_F6:
                        self.toggle_left_panel()
                        return True
        
            if not (self.serial and self.serial.is_open):
                return True
            
            # Arrow Up - Command history (previous command)
            if key == Qt.Key.Key_Up:
                self.handle_history_up()
                return True
            
            # Arrow Down - Command history (next command)
            elif key == Qt.Key.Key_Down:
                self.handle_history_down()
                return True
            
            # Printable character input
            elif text and text.isprintable() and not (modifiers & Qt.KeyboardModifier.ControlModifier):
                self.handle_character_input(text)
                return True
            
            # Enter key
            elif key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
                self.handle_enter()
                return True
            
            # Backspace key
            elif key == Qt.Key.Key_Backspace:
                self.handle_backspace()
                return True
            
            # Tab key (for autocomplete, etc.)
            elif key == Qt.Key.Key_Tab:
                self.handle_tab()
                return True
            
            return True
            
        return super().eventFilter(obj, event)

    def edit_current_command_list(self):
        """Open the currently selected predefined command list in an internal YAML editor."""
        file_path = self.current_cmdlist_file if self.current_cmdlist_file else utils.USER_COMMAND_LIST
        if not os.path.exists(file_path):
            QMessageBox.warning(self, "File Not Found", f"File does not exist:\n{file_path}")
            return
        dlg = YamlEditorDialog(file_path, self)
        dlg.exec()

    def show_shortcut_list(self):
        shortcuts = (
            "F1        : Show this shortcut list\n"
            "F2        : Connect Selected Serial Port\n"
            "F3        : Disconnect Serial port\n"
            "F4        : Open port list\n"
            "F5        : Refresh port list\n"
            "F6        : Expand/collapse left panel\n"
            "Ctrl + +  : Increase font size\n"
            "Ctrl + -  : Decrease font size\n"
            "Ctrl + 0  : Reset font size\n"
            "Ctrl + C  : Copy selection\n"
            "Ctrl + V  : Paste\n"
            "Alt + 0~9 : Send predefined command\n"
            "Up/Down   : Command history\n"
            "Enter     : Send input\n"
        )

        dlg = QDialog(self)
        dlg.setWindowTitle("Shortcut List")
        layout = QVBoxLayout(dlg)
        label = QLabel(shortcuts)
        label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setFont(QFont("Monaco", 11))
        layout.addWidget(label)
        btn = QPushButton("OK", dlg)
        btn.clicked.connect(dlg.accept)
        layout.addWidget(btn)
        dlg.setLayout(layout)
        dlg.exec()

    def handle_character_input(self, char):
        """Handle character input"""
        self.current_input_buffer += char
        self.history_index = -1  # Reset history index on new input
        
        # Display the input character immediately
        self.terminal_widget.append_text(char)
        self.show_current_input()

    def handle_backspace(self):
        """Handle backspace key"""
        if self.current_input_buffer:
            # Remove last character from buffer
            self.current_input_buffer = self.current_input_buffer[:-1]
            self.history_index = -1
            # Remove last character from terminal display
            self.terminal_widget.remove_last_char()
            self.show_current_input()

    def handle_enter(self):
        """Enter Key"""
        self.terminal_widget.append_text("\n")

        if self.current_input_buffer:
            command_to_send = self.current_input_buffer.rstrip() + "\r\n"
            self.serial.write(command_to_send.encode('utf-8', errors='replace'))
            
            # Add to command history
            if self.current_input_buffer in self.command_history:
                self.command_history.remove(self.current_input_buffer)
            self.command_history.insert(0, self.current_input_buffer)

            # Limit history size
            max_history = self.load_history_settings().get("max_count", 50)
            if len(self.command_history) > max_history:
                self.command_history = self.command_history[:max_history]

            # Clear buffer and reset index
            self.current_input_buffer = ""
            self.history_index = -1
        else:
            # Empty Enter
            self.serial.write(b"\r\n")
        
        self.show_current_input()

    def handle_history_up(self):
        """Move up in command history"""
        if self.command_history and self.history_index < len(self.command_history) - 1:
            self.clear_current_input_completely()
            self.history_index += 1
            self.current_input_buffer = self.command_history[self.history_index]
            self.terminal_widget.append_text(self.current_input_buffer)
            self.terminal_widget.set_cursor_to_end()

    def handle_history_down(self):
        """Move down in command history"""
        self.clear_current_input_completely()
        if self.history_index > 0:
            self.history_index -= 1
            self.current_input_buffer = self.command_history[self.history_index]
            self.terminal_widget.append_text(self.current_input_buffer)
        elif self.history_index == 0:
            self.history_index = -1
            self.current_input_buffer = ""
        self.terminal_widget.set_cursor_to_end()

    def handle_ctrl_c(self):
        """Ctrl+C: Copy selected block"""
        self.terminal_widget.copy_selection()

    def handle_paste(self):
        """Paste: Add clipboard text to input buffer and terminal"""
        clipboard = QGuiApplication.clipboard()
        text = clipboard.text()
        if text:
            # Support multi-line paste
            for line in text.splitlines(True):  # Keep line breaks
                self.current_input_buffer += line.rstrip('\r\n')
                self.terminal_widget.append_text(line)
            self.show_current_input()

    def handle_tab(self):
        """Tab key: Send input buffer + tab to serial, use response for autocomplete"""
        if not (self.serial and self.serial.is_open):
            return

        # Send input buffer + tab character
        tab_command = self.current_input_buffer + '\t'
        try:
            self.serial.write(tab_command.encode('utf-8', errors='replace'))
        except Exception as e:
            self.update_status_bar(f"Tab send error: {e}")
            return

        self.waiting_for_autocomplete = True  # Wait for autocomplete response
        self.terminal_widget.set_cursor_to_end()
        self.clear_current_input_completely()  # Clear current input line
        self.show_current_input()
        self.current_input_buffer = ""  # Reset input buffer

    def remove_last_char(self):
        if not self.lines:
            return
        if self.lines[-1]:
            last_text, last_color = self.lines[-1][-1]
            if len(last_text) > 1:
                self.lines[-1][-1] = (last_text[:-1], last_color)
            else:
                self.lines[-1].pop()
                if not self.lines[-1] and len(self.lines) > 1:
                    self.lines.pop()
        else:
            if len(self.lines) > 1:
                self.lines.pop()
                self.remove_last_char()
        self._schedule_update()

    def clear_current_input_completely(self):
        """Completely clear the current input line from the terminal (actually delete)"""
        if not self.terminal_widget.lines:
            self.current_input_buffer = ""
            return

        # Remove as many characters as the input buffer length from the last line
        total_len = len(self.current_input_buffer)
        if total_len > 0:
            line_parts = self.terminal_widget.lines[-1]
            line_text = self.terminal_widget._line_text(line_parts)
            # If the last line ends with the input buffer, remove that part
            if len(line_text) >= total_len:
                new_text = line_text[:-total_len]
                # Ignore color info, make a single line
                self.terminal_widget.lines[-1] = [(new_text, self.terminal_widget.default_color)] if new_text else []
            else:
                # If the whole line is shorter than the input, just clear it
                self.terminal_widget.lines[-1] = []
            self.terminal_widget._schedule_update()
        self.current_input_buffer = ""

    def clear_current_input(self):
        """Clear current input (legacy method)"""
        self.clear_current_input_completely()

    def show_current_input(self):
        """Show current input state in the status bar"""
        if hasattr(self, 'status'):
            if self.current_input_buffer:
                history_info = ""
                if self.command_history and self.history_index >= 0:
                    history_info = f" (History: {self.history_index + 1}/{len(self.command_history)})"
                # self.status.showMessage(f"Input: {self.current_input_buffer}{history_info}")
            # else:
            #     if self.serial and self.serial.is_open:
            #         self.status.showMessage("Connected - Ready for input")
            #     else:
            #         self.status.showMessage("Disconnected")
        # Update cursor position
        if self.terminal_widget.lines:
            line = len(self.terminal_widget.lines) - 1
            col = self.terminal_widget._line_length(self.terminal_widget.lines[-1])
            self.terminal_widget.set_cursor(line, col)

    def update_terminal(self, data):
        """Update terminal output"""
        # Apply ANSI spacing processing before displaying
        data = utils.process_ansi_spacing(data)
        self.terminal_widget.append_text(data)
        self.terminal_widget.update()  # or repaint() if needed

        # If autocomplete result arrived, update input buffer
        # Example: last input was tab, serial response is a single line (command)
        if hasattr(self, "waiting_for_autocomplete") and self.waiting_for_autocomplete:
            # Assume autocomplete result is a single line (with line break)
            lines = data.splitlines()
            if lines:
                self.show_current_input()
            self.waiting_for_autocomplete = False

    def clear_terminal(self):
        """Clear terminal"""
        self.terminal_widget.clear()

    def setup_terminal_font(self):
        """Terminal Font Settings"""
        fixed_font = QFont(self.load_font_settings().get("name", "Monaco"))
        fixed_font.setStyleHint(QFont.StyleHint.Monospace)
        fixed_font.setPointSize(self.font_size)
        self.terminal_widget.set_font(fixed_font)
    
        # Update the menu text to show current font size
        if hasattr(self, 'font_size_action'):
            self.font_size_action.setText(f"Current Font Size: {self.font_size}")

    def check_scroll_position(self):
        """Check scroll position (TerminalWidget handles this automatically)"""
        pass

    def save_recent_ports(self):
        # Save recent port list (YAML)
        try:
            with open(utils.USER_PORT_LIST, "w", encoding="utf-8") as f:
                yaml.safe_dump(self.recent_ports, f, allow_unicode=True, sort_keys=False)
        except Exception:
            pass

    def closeEvent(self, event):
        """Save history on application exit"""
        self.save_history_settings()
        if self.serial and self.serial.is_open:
            self.serial.close()
        super().closeEvent(event)

    def load_recent_ports(self):
        # Load recent port list from USER_PORT_LIST (YAML)
        try:
            with open(utils.USER_PORT_LIST, "r", encoding="utf-8") as f:
                ports = yaml.safe_load(f)
            return ports if ports else []
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
            with open(utils.USER_PORT_LIST, "w", encoding="utf-8") as f:
                yaml.safe_dump(ports, f, allow_unicode=True, sort_keys=False)
        except Exception:
            pass

    def update_status_bar(self, message):
        self.status.showMessage(message)
        
        if not message.startswith("Connect") and not message.startswith("Disconnect") and not message.startswith("Reconnect"):
            if self._status_timer.isActive():
                self._status_timer.stop()
            
            self._status_timer.start(2000)  # 2000ms

    def _restore_connection_status(self):
        if self.serial and self.serial.is_open:
            connection_status = f"Connected to {self.selected_port} @ {self.baudrate} bps"
        else:
            connection_status = "Disconnected"
        
        self.status.showMessage(connection_status)

    def update_config_file_status(self):
        """Update status bar to show current YAML file being used"""
        if self.current_cmdlist_file:
            filename = os.path.basename(self.current_cmdlist_file)
            if self.current_cmdlist_file == utils.USER_COMMAND_LIST:
                self.update_status_bar(f"Using default command list: {filename}")
                self.setWindowTitle("AT Commander v" + utils.APP_VERSION)
            else:
                self.update_status_bar(f"Using custom command list: {filename}")
                self.setWindowTitle("AT Commander v" + utils.APP_VERSION + f" - {filename}")
        else:
            self.update_status_bar("No command list loaded")
            self.setWindowTitle("AT Commander v" + utils.APP_VERSION)

    def show_about_dialog(self):
        QMessageBox.about(self, "About AT Commander", "AT Command Terminal Emulator\n\nVersion " + utils.APP_VERSION + "\n\nBy OllehEugene")

    def save_selected_config_filepath(self, file_path):
        """Save the last loaded YAML file path to settings"""
        try:
            # Load existing settings first
            settings = []
            if os.path.exists(utils.USER_SETTINGS):
                try:
                    with open(utils.USER_SETTINGS, "r", encoding="utf-8") as f:
                        settings = yaml.safe_load(f)
                    if not isinstance(settings, list):
                        settings = []
                except Exception:
                    settings = []
            
            # Find existing selected_commandlist_file object and update it
            config_file_found = False
            for item in settings:
                if isinstance(item, dict) and "last_cmdlist_file" in item:
                    item["last_cmdlist_file"] = file_path
                    config_file_found = True
                    break
            
            # If no last_cmdlist_file object found, add new one
            if not config_file_found:
                config_file_obj = {
                    "last_cmdlist_file": file_path
                }
                settings.append(config_file_obj)
            
            # Save back to file
            with open(utils.USER_SETTINGS, "w", encoding="utf-8") as f:
                yaml.safe_dump(settings, f, allow_unicode=True, sort_keys=False)
        except Exception as e:
            print(f"Warning: Could not save last YAML file setting: {e}")

    def load_selected_commandlist_file(self):
        """Load the last used YAML file path from settings"""
        try:
            with open(utils.USER_SETTINGS, "r", encoding="utf-8") as f:
                settings = yaml.safe_load(f)
                
                # Find last_cmdlist_file in the list
                for item in settings:
                    if isinstance(item, dict) and "last_cmdlist_file" in item:
                        return item["last_cmdlist_file"]
                
                return None
        except Exception:
            return None

    def auto_load_selected_commandlist_file(self):
        """Automatically load the last used YAML file on startup"""
        last_file = self.load_selected_commandlist_file()
        if last_file and os.path.exists(last_file) and last_file != utils.USER_COMMAND_LIST:
            try:
                self.load_and_validate_config_file(last_file, popup=True)
                # print(f"Auto-loaded last YAML file: {os.path.basename(last_file)}")
            except Exception as e:
                print(f"Could not auto-load last YAML file: {e}")
                # Fall back to default
                self.current_cmdlist_file = utils.USER_COMMAND_LIST
                self.update_config_file_status()

    def load_command_list_from_file(self):
        """Open file dialog to load command list from YAML file"""
        file_dialog = QFileDialog(self)
        file_dialog.setWindowTitle("Load Command List")
        file_dialog.setNameFilter("YAML files (*.yaml)")
        file_dialog.setFileMode(QFileDialog.ExistingFile)
        file_dialog.setAcceptMode(QFileDialog.AcceptOpen)
        
        from utils import get_user_config_path
        default_path = os.path.dirname(get_user_config_path("dummy"))
        

        # Set default directory to resources folder
        # default_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources")
        if os.path.exists(default_path):
            file_dialog.setDirectory(default_path)
        
        if file_dialog.exec():
            selected_files = file_dialog.selectedFiles()
            if selected_files:
                config_file_path = selected_files[0]
                self.load_and_validate_config_file(config_file_path, popup=True)

    def load_predefined_command_list(self, filename):
        """Loads a predefined command list based on its number."""
        from utils import get_user_config_path
        
        file_path = get_user_config_path(filename)
        
        if os.path.exists(file_path):
            self.load_and_validate_config_file(file_path, popup=False)
        else:
            QMessageBox.warning(
                self, 
                "File Not Found", 
                f"Predefined command list file not found:\n{os.path.basename(file_path)}"
            )

    def validate_config_structure(self, data):
        """Validate YAML file structure for command list"""
        if not isinstance(data, list):
            return False, "YAML file must contain an array of command objects"
        
        required_keys = ["index", "checked", "title", "time"]
        required_title_keys = ["text", "disabled"]
        
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                return False, f"Item {i} is not an object"
            
            # Check required keys
            for key in required_keys:
                if key not in item:
                    return False, f"Item {i} is missing required key: {key}"
            
            # Validate index
            if not isinstance(item["index"], int) or item["index"] < 0:
                return False, f"Item {i} has invalid index: must be a non-negative integer"
            
            # Validate checked
            if not isinstance(item["checked"], bool):
                return False, f"Item {i} has invalid checked value: must be boolean"
            
            # Validate title structure
            if not isinstance(item["title"], dict):
                return False, f"Item {i} has invalid title: must be an object"
            
            for title_key in required_title_keys:
                if title_key not in item["title"]:
                    return False, f"Item {i} title is missing required key: {title_key}"
            
            if not isinstance(item["title"]["text"], str):
                return False, f"Item {i} title text must be a string"
            
            if not isinstance(item["title"]["disabled"], bool):
                return False, f"Item {i} title disabled must be boolean"
            
            # Validate time
            if not isinstance(item["time"], (int, float)) or item["time"] < 0:
                return False, f"Item {i} has invalid time: must be a non-negative number"
        
        return True, "Valid YAML structure"

    def load_and_validate_config_file(self, file_path, popup=True):
        """Load and validate YAML file, then apply to command list"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            
            # Validate structure
            is_valid, message = self.validate_config_structure(data)
            
            if not is_valid:
                QMessageBox.critical(
                    self, 
                    "Invalid YAML File", 
                    f"The selected YAML file has an invalid\n\nPlease select a valid command list YAML file."
                )
                return
            
            # Apply the data to UI
            self.current_cmdlist_file = file_path  # Remember the current YAML file
            self.apply_config_data_to_ui(data)
            
            # Show success message
            if self.first_load != True:
                if popup:
                    QMessageBox.information(
                        self, 
                        "Success", 
                        f"Command list loaded successfully"
                    )
            else:
                self.first_load = False
            
            # Update status to show current YAML file
            self.update_config_file_status()
            
            # Save as last loaded YAML file for next startup
            self.save_selected_config_filepath(file_path)
            
        except yaml.YAMLError as e:
            QMessageBox.critical(
                self, 
                "YAML Parse Error", 
                f"The selected file is not a valid\n\nPlease select a valid YAML file."
            )
        except FileNotFoundError:
            QMessageBox.critical(
                self, 
                "File Not Found", 
                "The selected file could not be found."
            )
        except Exception as e:
            QMessageBox.critical(
                self, 
                "Error", 
                f"An error occurred while loading the file:\n\n{str(e)}"
            )

    def apply_config_data_to_ui(self, data):
        """Apply loaded YAML data to the UI elements and setup pagination."""
        self.full_command_list = sorted(data, key=lambda x: x['index'])
        self.current_page = 0
        
        self.setup_pagination()
        self.update_command_view()
        
        target_file = self.current_cmdlist_file if self.current_cmdlist_file else utils.USER_COMMAND_LIST
        try:
            with open(target_file, "w", encoding="utf-8") as f:
                yaml.safe_dump(self.full_command_list, f, allow_unicode=True, sort_keys=False)
        except Exception as e:
            self.update_status_bar(f"Warning: Could not save to {os.path.basename(target_file)}: {str(e)}")

    def setup_pagination(self):
        SerialTerminal.clear_layout(self.pagination_layout)

        num_pages = (len(self.full_command_list) - 1) // LINEEDIT_MAX_NUMBER + 1
        
        if num_pages > 1:
            self.pagination_group.show()
            self.page_buttons = []
            for i in range(num_pages):
                btn = QPushButton(str(i + 1))
                btn.setCheckable(True)
                btn.clicked.connect(lambda checked, page=i: self.go_to_page(page))
                self.pagination_layout.addWidget(btn)
                self.page_buttons.append(btn)
            
            # self.pagination_layout.addStretch()
            if self.page_buttons:
                self.page_buttons[self.current_page].setChecked(True)
        else:
            self.pagination_group.hide()

    def go_to_page(self, page_number):
        self.load_checkbox_lineedit(self.current_cmdlist_file)
        if self.current_page == page_number:
            self.page_buttons[page_number].setChecked(True)
            return

        self.page_buttons[self.current_page].setChecked(False)
        self.current_page = page_number
        self.page_buttons[self.current_page].setChecked(True)
        
        self.update_command_view()

    def update_command_view(self):
        start_index_in_list = self.current_page * LINEEDIT_MAX_NUMBER
        end_index_in_list = start_index_in_list + LINEEDIT_MAX_NUMBER
        commands_for_page = self.full_command_list[start_index_in_list:end_index_in_list]

        for i in range(LINEEDIT_MAX_NUMBER):
            self.checkboxes[i].stateChanged.disconnect()
            self.lineedits[i].textChanged.disconnect()
            self.checkboxes[i].setVisible(False)
            self.lineedits[i].setVisible(False)
            self.sendline_btns[i].setVisible(False)
            self.lineedits[i].setText("")
            self.checkboxes[i].setChecked(False)
            self.checkboxes[i].stateChanged.connect(lambda state, idx=i: self.save_checkbox_lineedit())
            self.lineedits[i].textChanged.connect(lambda text, idx=i: self.save_checkbox_lineedit())

        for item in commands_for_page:

            original_index = item["index"]
            ui_index = original_index % LINEEDIT_MAX_NUMBER
            self.checkboxes[ui_index].stateChanged.disconnect()
            self.lineedits[ui_index].textChanged.disconnect()

            self.checkboxes[ui_index].setVisible(True)
            self.lineedits[ui_index].setVisible(True)
            self.sendline_btns[ui_index].setVisible(True)

            self.checkboxes[ui_index].setChecked(item["checked"])
            self.lineedits[ui_index].setText(item["title"]["text"])
            
            disabled = item.get("title", {}).get("disabled", False)
            self.checkboxes[ui_index].setDisabled(disabled)
            self.lineedits[ui_index].setDisabled(disabled)
            self.sendline_btns[ui_index].setDisabled(disabled)
            
            self.checkboxes[ui_index].setVisible(not disabled)
            self.sendline_btns[ui_index].setVisible(not disabled)
            self.checkboxes[ui_index].stateChanged.connect(lambda state, idx=i: self.save_checkbox_lineedit())
            self.lineedits[ui_index].textChanged.connect(lambda text, idx=i: self.save_checkbox_lineedit())

            if disabled:
                self.lineedits[ui_index].setAlignment(Qt.AlignCenter)
            else:
                self.lineedits[ui_index].setAlignment(Qt.AlignLeft)

    def apply_theme(self, theme_name):
        if theme_name == "default":
            QApplication.instance().setStyleSheet("")
        else:
            theme_path = utils.get_resources(theme_name+".css")
            if os.path.exists(theme_path):
                with open(theme_path, "r") as f:
                    style = f.read()
                    QApplication.instance().setStyleSheet(style)
        self.save_theme_settings(theme_name)


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
            self.connect_btn.setToolTip(f"Connect Serial Port")
        else:
            try:
                self.serial = serial.Serial(self.selected_port, self.baudrate, timeout=0.1)
                self.running = True
                self.thread = threading.Thread(target=self.read_serial_data, daemon=True)
                self.thread.start()
                self.update_status_bar(f"Connected to {self.selected_port} @ {self.baudrate} bps")
                self.connect_btn.setChecked(True)
                self.connect_btn.setText("Disconnect")
                self.save_recent_port(self.selected_port)  # Save recent port
                self.connect_btn.setToolTip(f"Disconnect Serial Port")
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

    def _setup_serial_group_layout(self, horizontal=False):
        
        self.port_label.setParent(None)
        self.serial_port_combo.setParent(None)
        self.baud_label.setParent(None)
        self.baudrate_combo.setParent(None)
        self.connect_btn.setParent(None)
        self.refresh_btn.setParent(None)

        if self.serial_group.layout() is not None:
            QWidget().setLayout(self.serial_group.layout())

        if horizontal:
            layout = QHBoxLayout()
            layout.setSpacing(0)
            layout.setContentsMargins(5, 2, 5, 2)
            
            layout.addWidget(self.port_label)
            layout.addWidget(self.serial_port_combo)
            layout.addWidget(self.baud_label)
            layout.addWidget(self.baudrate_combo)
            layout.addWidget(self.connect_btn)
            layout.addWidget(self.refresh_btn)

            self.serial_group.setTitle("")
            self.serial_group.setMinimumWidth(450) 
            self.serial_group.setMinimumHeight(45)
        else:
            layout = QVBoxLayout()
            layout.setSpacing(0)
            layout.setContentsMargins(0, 0, 0, 0)
            
            port_layout = QHBoxLayout()
            port_layout.setContentsMargins(0, 0, 0, 0)
            port_layout.addWidget(self.port_label)
            port_layout.addWidget(self.serial_port_combo)
            
            baud_btn_layout = QHBoxLayout()
            baud_btn_layout.setSpacing(0)
            baud_btn_layout.setContentsMargins(5, 0, 5, 0)
            baud_btn_layout.addWidget(self.baud_label)
            baud_btn_layout.addWidget(self.baudrate_combo)
            baud_btn_layout.addWidget(self.connect_btn)
            baud_btn_layout.addWidget(self.refresh_btn)
            
            layout.addLayout(port_layout)
            layout.addLayout(baud_btn_layout)

            self.serial_group.setTitle("Serial Settings")
            self.serial_group.setMinimumWidth(0)
            self.serial_group.setMinimumHeight(0)
            
        self.serial_group.setLayout(layout)

    def toggle_left_panel(self):
        if self.left_panel_visible:
            self.toggle_btn.setIcon(QIcon(utils.get_resources(utils.RIGHT_ARROW_ICON_NAME)))
            self.serial_group.setParent(None)
            self._setup_serial_group_layout(horizontal=True)
            self.top_right_btn_layout.setSpacing(0)
            self.top_right_btn_layout.setContentsMargins(0, 0, 0, 0)
            self.right_layout.setSpacing(0)
            self.right_layout.setContentsMargins(0, 0, 8, 12)
            self.top_right_btn_layout.insertWidget(0, self.serial_group)
            self.splitter.widget(0).hide()
        else:
            self.toggle_btn.setIcon(QIcon(utils.get_resources(utils.LEFT_ARROW_ICON_NAME)))
            self.serial_group.setParent(None)
            self._setup_serial_group_layout(horizontal=False)
            self.left_layout.insertWidget(0, self.serial_group)

            self.splitter.widget(0).show()

        self.left_panel_visible = not self.left_panel_visible
        self.terminal_widget.update_scrollbar()

    def send_lineedit_command(self, index):
        command = self.lineedits[index].text()
        
        if command and self.serial and self.serial.is_open:
            try:
                # Add command to history
                if command not in self.command_history:
                    self.command_history.insert(0, command)
                    if len(self.command_history) > self.load_history_settings().get("max_count", 50):
                        self.command_history.pop()
                
                # Send command with carriage return and line feed
                command_bytes = (command + "\r\n").encode('utf-8', errors='replace')
                bytes_written = self.serial.write(command_bytes)
                
                # Update status bar with success message
                # self.update_status_bar(f"Sent: {command}")
                
                # Display sent command in terminal for verification
                self.serial_data_signal.emit(f"{command}\r\n")
                
            except Exception as e:
                # Handle encoding or serial errors
                self.update_status_bar(f"Send error: {str(e)}")
        elif not self.serial or not self.serial.is_open:
            self.update_status_bar("Error: Not connected to serial port")
        elif not command:
            self.update_status_bar("Error: No command to send")

    def save_checkbox_lineedit(self, filename=None):
        # Update the in-memory list first
        for i in range(LINEEDIT_MAX_NUMBER):
            if not self.lineedits[i].isVisible():
                continue

            original_index = self.current_page * LINEEDIT_MAX_NUMBER + i
            
            for item in self.full_command_list:
                if item['index'] == original_index:
                    item['checked'] = self.checkboxes[i].isChecked()
                    item['title']['text'] = self.lineedits[i].text()
                    break
        
        if filename is None:
            filename = self.current_cmdlist_file if self.current_cmdlist_file else utils.USER_COMMAND_LIST
        
        try:
            with open(filename, "w", encoding="utf-8") as f:
                yaml.safe_dump(self.full_command_list, f, allow_unicode=True, sort_keys=False)
        except Exception as e:
            self.update_status_bar(f"Warning: Could not save to {os.path.basename(filename)}: {str(e)}")

    def load_checkbox_lineedit(self, filename):
        # YAML 버전
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception:
            data = []
        # ...기존 UI 반영 코드...
        self.apply_config_data_to_ui(data)

    def read_serial_data(self):
        """Thread function to read serial data"""
        buffer_start_time = None
        emit_batch = []

        while self.running and self.serial and self.serial.is_open:
            try:
                if self.serial.in_waiting > 0:
                    data_bytes = self.serial.read(self.serial.in_waiting)
                    try:
                        data_str = data_bytes.decode('utf-8', errors='replace')
                    except UnicodeDecodeError:
                        data_str = data_bytes.decode('latin-1', errors='replace')

                    if data_str:
                        combined_data = self.ansi_buffer + data_str
                        self.ansi_buffer = ""

                        lines = re.split(r'(\r\n|\n|\r)', combined_data)
                        i = 0
                        while i < len(lines) - 1:
                            line = lines[i]
                            sep = lines[i+1]
                            full_line = line + sep
                            is_complete, incomplete_pos = utils.is_ansi_sequence_complete(full_line)
                            if is_complete:
                                emit_batch.append(full_line)
                            else:
                                self.ansi_buffer = full_line + ''.join(lines[i+2:])
                                break
                            i += 2

                        if i == len(lines) - 1:
                            self.ansi_buffer = lines[i]
                        buffer_start_time = time.time()

                    # Emit multiple lines at once (performance improvement)
                    if emit_batch:
                        for chunk in emit_batch:
                            self.serial_data_signal.emit(chunk)
                        emit_batch.clear()
                else:
                    # Check for buffer timeout (50ms)
                    if self.ansi_buffer:
                        if buffer_start_time is not None and (time.time() - buffer_start_time > 0.05):
                            self.serial_data_signal.emit(self.ansi_buffer)
                            self.ansi_buffer = ""
                            buffer_start_time = None
                time.sleep(0.001)  # Shorter sleep (if CPU is idle)
            except serial.SerialException:
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
                try:
                    if self.serial and self.serial.is_open:
                        self.serial.close()
                except Exception:
                    pass
                self.reconnect_signal.emit()
                self.connect_btn.setChecked(False)
                self.connect_btn.setText("Connect")
                self.running = False
                break

    def sequential_send_commands(self):
        if self.serial and self.serial.is_open:
            # Collect all commands to send with their time intervals
            commands_to_send = []
            
            # Load time intervals from YAML file
            time_intervals = {}
            try:
                with open(utils.USER_COMMAND_LIST, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if isinstance(data, list):
                    for item in data:
                        idx = item.get("index")
                        if idx is not None:
                            time_intervals[idx] = item.get("time", 1.0)  # Default 1 second
            except Exception:
                pass
            
            for i in range(LINEEDIT_MAX_NUMBER):
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
                                self.serial_data_signal.emit(f"{command}\r\n")
                                
                                # Add to history
                                if command not in self.command_history:
                                    self.command_history.insert(0, command)
                                    if len(self.command_history) > self.load_history_settings().get("max_count", 50):
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

    def load_history_settings(self):
        """히스토리 설정 로딩"""
        try:
            if os.path.exists(utils.USER_SETTINGS):
                try:
                    with open(utils.USER_SETTINGS, "r", encoding="utf-8") as f:
                        user_settings_file = yaml.safe_load(f)
                        # Find last_cmdlist_file in the list
                        for item in user_settings_file:
                            if isinstance(item, dict) and "history_settings" in item:
                                return item["history_settings"]
                    if not isinstance(item, dict):
                        history_file = {"max_count": 50, "save_on_exit": True, "history": []}
                    return history_file
                except Exception:
                    history_file = {"max_count": 50, "save_on_exit": True, "history": []}
                    return history_file
        except Exception as e:
            print(f"Error loading history settings: {e}")
            return {"max_count": 50, "save_on_exit": True}

    def save_history_settings(self):
        """Store history settings"""
        try:
            history_settings = {
                "max_count": 50,
                "save_on_exit": True,
                "history": self.command_history[:50]
            }
            # Load existing settings first
            settings = []
            if os.path.exists(utils.USER_SETTINGS):
                try:
                    with open(utils.USER_SETTINGS, "r", encoding="utf-8") as f:
                        settings = yaml.safe_load(f)
                    if not isinstance(settings, list):
                        settings = []
                except Exception:
                    settings = []
            
            # Find existing font object and update it
            for item in settings:
                if isinstance(item, dict) and "history_settings" in item:
                    # Update only the size, keep other font properties
                    item["history_settings"] = history_settings
                    item_found = True
                    break
            
            # If no font object found, add new one
            if not item_found:
                history_obj = {
                    "history_settings": {
                    "max_count": 50,
                    "save_on_exit": True,
                    "history": []
                    },
                }
                settings.append(history_obj)
            
            # Save back to file
            with open(utils.USER_SETTINGS, "w", encoding="utf-8") as f:
                yaml.safe_dump(settings, f, allow_unicode=True, sort_keys=False)
        except Exception as e:
            print(f"Warning: Could not save theme settings: {e}")

    def load_command_history(self):
        """명령 히스토리 로딩"""
        try:
            settings = self.load_history_settings()
            # self.command_history = settings.get("history_settings", [])
            self.command_history = settings.get("history", [])
        except Exception as e:
            print(f"Error loading command history: {e}")
            self.command_history = []
    
    def load_font_settings(self):
        """Load font settings from file or return default"""
        font_info = {}
        try:
            with open(utils.USER_SETTINGS, "r", encoding="utf-8") as f:
                settings = yaml.safe_load(f)
                
                # Find font object in the list
                for item in settings:
                    if isinstance(item, dict) and "font" in item:
                        font_info = item["font"]
                        # font_size = font_info.get("size", 14)
                        break

                # Validate font size range
                if (font_info.get("size", 14) > 32) or (font_info.get("size", 14) < 6):
                    font_info.setdefault("size", 14)
                return font_info
        except Exception:
            font_info.setdefault("size", 14)
            font_info.setdefault("family", "Monaco")
            font_info.setdefault("bold", False)
            return font_info

    def load_theme_settings(self):
        """Load th eme settings from file or return default"""
        try:
            with open(utils.USER_SETTINGS, "r", encoding="utf-8") as f:
                settings = yaml.safe_load(f)

                for item in settings:
                    if isinstance(item, dict) and "theme" in item:
                        theme_settings = item["theme"]
                        return theme_settings

        except Exception:
            return "default"

    def save_theme_settings(self, theme_name):
        try:
            # Load existing settings first
            settings = []
            if os.path.exists(utils.USER_SETTINGS):
                try:
                    with open(utils.USER_SETTINGS, "r", encoding="utf-8") as f:
                        settings = yaml.safe_load(f)
                    if not isinstance(settings, list):
                        settings = []
                except Exception:
                    settings = []
            
            # Find existing font object and update it
            for item in settings:
                if isinstance(item, dict) and "theme" in item:
                    # Update only the size, keep other font properties
                    item["theme"] = theme_name
                    theme_found = True
                    break
            
            # If no font object found, add new one
            if not theme_found:
                theme_obj = {
                    "theme": "default"
                }
                settings.append(theme_obj)
            
            # Save back to file
            with open(utils.USER_SETTINGS, "w", encoding="utf-8") as f:
                yaml.safe_dump(settings, f, allow_unicode=True, sort_keys=False)
        except Exception as e:
            print(f"Warning: Could not save theme settings: {e}")

    def save_font_settings(self):
        """Save current font settings to file"""
        try:
            # Load existing settings first
            settings = []
            if os.path.exists(utils.USER_SETTINGS):
                try:
                    with open(utils.USER_SETTINGS, "r", encoding="utf-8") as f:
                        settings = yaml.safe_load(f)
                    if not isinstance(settings, list):
                        settings = []
                except Exception:
                    settings = []
            
            # Find existing font object and update it
            font_found = False
            for item in settings:
                if isinstance(item, dict) and "font" in item:
                    # Update only the size, keep other font properties
                    item["font"]["size"] = self.font_size
                    font_found = True
                    break
            
            # If no font object found, add new one
            if not font_found:
                font_obj = {
                    "font": {
                        "name": "Monaco",
                        "size": self.font_size,
                        "bold": False
                    }
                }
                settings.append(font_obj)
            
            # Save back to file
            with open(utils.USER_SETTINGS, "w", encoding="utf-8") as f:
                yaml.safe_dump(settings, f, allow_unicode=True, sort_keys=False)
        except Exception as e:
            print(f"Warning: Could not save font settings: {e}")

    def setup_terminal_font(self):
        """Setup terminal font with current font size"""
        fixed_font = QFont(self.load_font_settings().get("name", "Monaco"))
        fixed_font.setStyleHint(QFont.StyleHint.Monospace)
        fixed_font.setPointSize(self.font_size)
        self.terminal_widget.set_font(fixed_font)
        
        # Update the menu text to show current font size
        if hasattr(self, 'font_size_action'):
            self.font_size_action.setText(f"Current Font Size: {self.font_size}")
    
    def increase_font_size(self):
        """Increase terminal font size"""
        if self.font_size < 32:  # Maximum font size limit
            self.font_size += 1
            self.setup_terminal_font()
            self.save_font_settings()
            self.update_status_bar(f"Font size: {self.font_size}")
    
    def decrease_font_size(self):
        """Decrease terminal font size"""
        if self.font_size > 6:  # Minimum font size limit
            self.font_size -= 1
            self.setup_terminal_font()
            self.save_font_settings()
            self.update_status_bar(f"Font size: {self.font_size}")
    
    def reset_font_size(self):
        """Reset terminal font size to default"""
        self.font_size = 11  # Default font size
        self.setup_terminal_font()
        self.save_font_settings()
        self.update_status_bar(f"Font size reset to: {self.font_size}")
    
    def check_scroll_position(self):
        """Check scroll position (TerminalWidget handles automatically)"""
        # This function is intentionally left blank as TerminalWidget manages scrolling automatically
        pass

    def try_reconnect_serial(self):
        if self.serial and self.serial.is_open:
            return
        try:
            self.serial = serial.Serial(self.selected_port, self.baudrate, timeout=0.1)
            self.running = True
            self.thread = threading.Thread(target=self.read_serial_data, daemon=True)
            self.thread.start()
            self.update_status_bar(f"Reconnected to {self.selected_port} @ {self.baudrate} bps")
            self.connect_btn.setChecked(True)
            self.connect_btn.setText("Disconnect")
            self.save_recent_port(self.selected_port)
        except serial.SerialException as e:
            self.update_status_bar(f"Reconnect failed: {e}")
            QTimer.singleShot(500, self.try_reconnect_serial)

    def open_config_folder(self):
        from utils import get_user_config_path
        config_path = get_user_config_path("dummy")
        config_dir = os.path.dirname(config_path)

        try:
            subprocess.Popen(["open", config_dir])
        except Exception as e:
            self.update_status_bar(f"Could not open config folder: {e}")