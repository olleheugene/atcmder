import os
import yaml
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QGroupBox, QFormLayout, QFontComboBox, QSpinBox, QCheckBox,
    QPushButton, QComboBox, QLabel, QMessageBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont 
import utils

SETTINGS_PATH = os.path.join(
    os.path.dirname(__file__), "resources", "atcmder_settings.yaml"
)

class OutputTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()

        # Font settings
        font_group = QGroupBox("Font Settings")
        font_layout = QVBoxLayout()

        # Font name
        font_name_layout = QHBoxLayout()
        font_name_label = QLabel("Font:")
        self.font_combo = QFontComboBox()
        font_name_layout.addWidget(font_name_label)
        font_name_layout.addWidget(self.font_combo)
        font_name_layout.addStretch()
        font_layout.addLayout(font_name_layout)

        # Font size
        font_size_layout = QHBoxLayout()
        font_size_label = QLabel("Font Size:")
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(6, 32)
        self.font_size_spin.setMinimumWidth(70)

        font_size_layout.addWidget(font_size_label)
        font_size_layout.addWidget(self.font_size_spin)
        font_size_layout.addStretch()
        font_layout.addLayout(font_size_layout)

        # Font bold
        font_bold_layout = QHBoxLayout()
        self.font_bold_check = QCheckBox("Bold")
        font_bold_layout.addWidget(self.font_bold_check)
        font_bold_layout.addStretch()
        font_layout.addLayout(font_bold_layout)

        font_group.setLayout(font_layout)
        layout.addWidget(font_group)

        # Output window settings
        output_group = QGroupBox("Terminal Window Settings")
        output_layout = QFormLayout()

        self.line_number_check = QCheckBox("Show Line Numbers")
        output_layout.addRow(self.line_number_check)

        self.show_time_check = QCheckBox("Show Output Time")
        output_layout.addRow(self.show_time_check)

        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        # History settings
        history_group = QGroupBox("History Settings")
        history_layout = QFormLayout()
        
        self.max_count_spin = QSpinBox()
        self.max_count_spin.setRange(10, 1000)
        self.max_count_spin.setValue(50)
        self.max_count_spin.setMinimumWidth(70)
        history_layout.addRow("Maximum History Count:", self.max_count_spin)
        
        self.auto_save_check = QCheckBox("Auto-save history")
        self.auto_save_check.setChecked(True)
        history_layout.addRow(self.auto_save_check)
        
        history_group.setLayout(history_layout)
        layout.addWidget(history_group)
        
        # History management
        management_group = QGroupBox("History Management")
        management_layout = QVBoxLayout()
        
        self.clear_history_btn = QPushButton("Clear All History")
        self.clear_history_btn.clicked.connect(self.clear_history)
        management_layout.addWidget(self.clear_history_btn)
        
        # Show current history count
        self.history_count_label = QLabel()
        self.update_history_count()
        management_layout.addWidget(self.history_count_label)
        
        management_group.setLayout(management_layout)
        layout.addWidget(management_group)

        layout.addStretch()
        self.setLayout(layout)

    def clear_history(self):
        reply = QMessageBox.question(
            self, 
            "Clear History", 
            "Are you sure you want to clear all command history?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            import utils
            if utils.clear_command_history():
                QMessageBox.information(self, "Success", "Command history cleared successfully.")
                self.update_history_count()
            else:
                QMessageBox.warning(self, "Error", "Failed to clear command history.")
    
    def update_history_count(self):
        import utils
        history = utils.load_command_history()
        self.history_count_label.setText(f"Current history entries: {len(history)}")

    def load_settings(self, settings):
        # Load font settings
        self.font_combo.setCurrentText(settings['font']['name'])
        self.font_size_spin.setValue(settings['font']['size'])
        self.font_bold_check.setChecked(settings['font'].get('bold', False))
        
        # Load output window settings
        self.line_number_check.setChecked(settings.get('output_window', {}).get('show_line_numbers', False))
        self.show_time_check.setChecked(settings.get('output_window', {}).get('show_time', False))
        
        # Load history settings
        import utils
        history_settings = utils.get_history_settings()
        self.max_count_spin.setValue(history_settings.get("max_count", 50))
        self.auto_save_check.setChecked(history_settings.get("auto_save", True))
        self.update_history_count()

    def save_settings(self, settings):
        # Save font settings
        settings['font']['name'] = self.font_combo.currentText()
        settings['font']['size'] = self.font_size_spin.value()
        settings['font']['bold'] = self.font_bold_check.isChecked()
        
        # Save output window settings
        settings['output_window']['show_line_numbers'] = self.line_number_check.isChecked()
        settings['output_window']['show_time'] = self.show_time_check.isChecked()
        
        # Save history settings
        import utils
        current_history = utils.load_command_history()
        utils.save_command_history(current_history, self.max_count_spin.value())

class WindowsTab(QWidget):
    def __init__(self, parent_dialog=None):
        super().__init__()
        self.parent_dialog = parent_dialog
        layout = QVBoxLayout()
        
        # Theme settings
        theme_group = QGroupBox("Theme Settings")
        theme_layout = QVBoxLayout()

        # Theme selection
        theme_selection_layout = QHBoxLayout()
        theme_label = QLabel("Theme:")
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["default", "dark", "light"])
        theme_selection_layout.addWidget(theme_label)
        theme_selection_layout.addWidget(self.theme_combo)
        theme_selection_layout.addStretch()
        theme_layout.addLayout(theme_selection_layout)

        theme_group.setLayout(theme_layout)
        layout.addWidget(theme_group)
        
        # Command Group settings
        command_group = QGroupBox("Command Group Settings")
        command_layout = QFormLayout()
        
        self.command_group_spin = QSpinBox()
        self.command_group_spin.setRange(3, 10)
        self.command_group_spin.setValue(3)
        self.command_group_spin.setMinimumWidth(70)
        command_layout.addRow("Number of Command Groups:", self.command_group_spin)
        
        # Description label
        info_label = QLabel("Set the number of command group buttons to display.\nRange: 3 to 10 buttons")
        info_label.setStyleSheet("color: #666; font-size: 11px;")
        command_layout.addRow(info_label)
        
        command_group.setLayout(command_layout)
        layout.addWidget(command_group)
        
        # HEX Mode settings
        hex_mode_group = QGroupBox("HEX Mode Settings")
        hex_mode_layout = QVBoxLayout()
        
        self.keep_hex_mode_check = QCheckBox("Keeping HEX mode")
        self.keep_hex_mode_check.setToolTip("When enabled, commands with hexmode=true in YAML will be displayed in HEX mode on startup")
        hex_mode_layout.addWidget(self.keep_hex_mode_check)
        
        # Description label
        hex_info_label = QLabel("If checked, commands marked with 'hexmode: true' in YAML files\nwill automatically switch to HEX mode when the application starts.")
        hex_info_label.setStyleSheet("color: #666; font-size: 11px;")
        hex_mode_layout.addWidget(hex_info_label)
        
        hex_mode_group.setLayout(hex_mode_layout)
        layout.addWidget(hex_mode_group)
        
        layout.addStretch()
        self.setLayout(layout)
    
    def load_settings(self, settings):
        # Load Theme setting
        self.theme_combo.setCurrentText(settings.get('theme', 'default'))
        
        # Load Keep HEX mode setting
        self.keep_hex_mode_check.setChecked(settings.get('keep_hex_mode', False))
        
        # Load Command Group count
        try:
            import yaml
            with open(utils.USER_SETTINGS, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            # Find command_group_count at the top level
            if "command_group_count" in data:
                count = data["command_group_count"]
                self.command_group_spin.setValue(max(3, min(10, count)))
                return

            self.command_group_spin.setValue(3)  # default value
        except Exception:
            self.command_group_spin.setValue(3)  # default value

    def save_settings(self, settings):
        # Save Theme setting
        settings['theme'] = self.theme_combo.currentText()
        
        # Save Keep HEX mode setting
        settings['keep_hex_mode'] = self.keep_hex_mode_check.isChecked()
        
        # Save Command Group count and update UI
        new_count = self.command_group_spin.value()
        
        try:
            # Save to settings dictionary (saved to file in settings_dialog.py's save_settings)
            settings["command_group_count"] = new_count

            # Update Command Group buttons in parent window
            if (self.parent_dialog and
                hasattr(self.parent_dialog, 'parent_window') and
                self.parent_dialog.parent_window and
                hasattr(self.parent_dialog.parent_window, 'update_command_group_buttons')):
                self.parent_dialog.parent_window.update_command_group_buttons(new_count)
        except Exception as e:
            print(f"Warning: Could not update command group buttons: {e}")

class SettingsDialog(QDialog):
    def __init__(self, parent=None, settings_path=None, on_settings_changed=None):
        super().__init__(parent)
        self.settings_path = settings_path
        self.on_settings_changed = on_settings_changed
        self.parent_window = parent  # Store parent reference
        self.setWindowTitle("Settings")
        self.resize(500, 400)
        self.setModal(True)  # Set as modal dialog
        
        layout = QVBoxLayout()
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        
        # Create tabs
        self.output_tab = OutputTab()
        self.windows_tab = WindowsTab(self)  # Pass parent dialog reference
        
        # Add tabs
        self.tab_widget.addTab(self.output_tab, "Terminal")
        self.tab_widget.addTab(self.windows_tab, "Window")
        
        layout.addWidget(self.tab_widget)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.apply_btn = QPushButton("Apply")
        self.ok_btn = QPushButton("OK")
        self.cancel_btn = QPushButton("Cancel")
        
        self.apply_btn.clicked.connect(self.apply_settings)
        self.ok_btn.clicked.connect(self.accept_settings)
        self.cancel_btn.clicked.connect(self.cancel_settings)
        
        button_layout.addWidget(self.apply_btn)
        button_layout.addWidget(self.ok_btn)
        button_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
        
        # Initialize settings
        self.settings = {}
        
        # Load current settings
        self.settings = self.load_settings()

        # Call parent's apply_settings if callback is provided
        if self.on_settings_changed:
            self.on_settings_changed(self.settings)

    def load_settings(self):
        """Load settings from YAML file"""
        if not self.settings_path or not os.path.exists(self.settings_path):
            # Return default settings
            settings = {
                'font': {'name': 'Monaco', 'size': 11, 'bold': False},
                'theme': 'default',
                'output_window': {'show_line_numbers': False, 'show_time': False}
            }
        else:
            try:
                with open(self.settings_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                
                # Convert list of dicts to flat dict for easy access
                settings = {}

                # Check if new format (dictionary) is used
                if isinstance(data, dict):
                    # New format - use keys directly
                    settings = data.copy()
                elif isinstance(data, list):
                    # Old format - extract from list
                    for item in data:
                        if isinstance(item, dict):
                            if 'font' in item:
                                settings['font'] = item['font']
                            if 'theme' in item:
                                settings['theme'] = item['theme']
                            if 'output_window' in item:
                                settings['output_window'] = item['output_window']
                else:
                    settings = data or {}
                
                # Ensure defaults
                settings.setdefault('font', {'name': 'Monaco', 'size': 11, 'bold': False})
                settings.setdefault('theme', 'default')
                settings.setdefault('output_window', {'show_line_numbers': False, 'show_time': False})
                
            except Exception as e:
                print(f"Error loading settings: {e}")
                settings = {
                    'font': {'name': 'Monaco', 'size': 11, 'bold': False},
                    'theme': 'default',
                    'output_window': {'show_line_numbers': False, 'show_time': False}
                }
        
        # Load settings into tabs
        self.output_tab.load_settings(settings)
        self.windows_tab.load_settings(settings)
        
        return settings

    def save_settings(self):
        """Save settings to YAML file"""
        if not self.settings_path:
            return
        
        # Update settings from tabs
        self.output_tab.save_settings(self.settings)
        self.windows_tab.save_settings(self.settings)
        
        try:
            # Check if existing file is present and determine structure
            existing_data = {}
            is_new_format = False
            
            if os.path.exists(self.settings_path):
                with open(self.settings_path, "r", encoding="utf-8") as f:
                    existing_data = yaml.safe_load(f) or {}
                    
                if isinstance(existing_data, dict) and "command_group_count" in existing_data:
                    is_new_format = True
                else:
                    is_new_format = False

            # Save in new format (use top-level keys)
            data = {}
            data['font'] = self.settings['font']
            data['theme'] = self.settings['theme']
            data['output_window'] = self.settings['output_window']
            
            if 'command_group_count' in self.settings:
                data['command_group_count'] = self.settings['command_group_count']
            
            if 'keep_hex_mode' in self.settings:
                data['keep_hex_mode'] = self.settings['keep_hex_mode']      

            # Ensure directory exists
            os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
            
            with open(self.settings_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
                
        except Exception as e:
            print(f"Error saving settings: {e}")

    def apply_settings(self):
        """Apply settings immediately to the UI"""
        try:
            # Update settings from tabs first
            self.output_tab.save_settings(self.settings)
            self.windows_tab.save_settings(self.settings)
            
            # Save to file
            self.save_settings()
            
            # Call parent's apply_settings if callback is provided
            if self.on_settings_changed:
                self.on_settings_changed(self.settings)
        except Exception as e:
            print(f"Error applying settings: {e}")

    def accept_settings(self):
        """Apply settings and close dialog"""
        try:
            self.apply_settings()
            self.accept()
        except Exception as e:
            print(f"Error accepting settings: {e}")
            self.accept()
    
    def cancel_settings(self):
        """Cancel settings and close dialog"""
        self.reject()