import os
import yaml
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QGroupBox, QFormLayout, QFontComboBox, QSpinBox, QCheckBox,
    QPushButton, QComboBox, QLabel, QMessageBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont  # QFont import 추가
import utils

SETTINGS_PATH = os.path.join(
    os.path.dirname(__file__), "resources", "atcmder_settings.yaml"
)

class FontTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()

        # Font settings
        font_group = QGroupBox("Font Settings")
        font_layout = QFormLayout()

        self.font_combo = QFontComboBox()
        font_layout.addRow("Font:", self.font_combo)

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(6, 32)
        font_layout.addRow("Font Size:", self.font_size_spin)

        self.font_bold_check = QCheckBox("Bold")
        font_layout.addRow(self.font_bold_check)

        font_group.setLayout(font_layout)
        layout.addWidget(font_group)

        layout.addStretch()
        self.setLayout(layout)

    def load_settings(self, settings):
        self.font_combo.setCurrentText(settings['font']['name'])
        self.font_size_spin.setValue(settings['font']['size'])
        self.font_bold_check.setChecked(settings['font'].get('bold', False))

    def save_settings(self, settings):
        settings['font']['name'] = self.font_combo.currentText()
        settings['font']['size'] = self.font_size_spin.value()
        settings['font']['bold'] = self.font_bold_check.isChecked()

class OutputTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()

        # Output window settings
        output_group = QGroupBox("Output Window Settings")
        output_layout = QFormLayout()

        self.line_number_check = QCheckBox("Show Line Numbers")
        output_layout.addRow(self.line_number_check)

        self.show_time_check = QCheckBox("Show Output Time")
        output_layout.addRow(self.show_time_check)

        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        layout.addStretch()
        self.setLayout(layout)

    def load_settings(self, settings):
        self.line_number_check.setChecked(settings.get('output_window', {}).get('show_line_numbers', False))
        self.show_time_check.setChecked(settings.get('output_window', {}).get('show_time', False))

    def save_settings(self, settings):
        settings['output_window']['show_line_numbers'] = self.line_number_check.isChecked()
        settings['output_window']['show_time'] = self.show_time_check.isChecked()

class HistoryTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()
        
        # History settings
        history_group = QGroupBox("History Settings")
        history_layout = QFormLayout()
        
        self.max_count_spin = QSpinBox()
        self.max_count_spin.setRange(10, 1000)
        self.max_count_spin.setValue(50)
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
        import utils
        history_settings = utils.get_history_settings()
        self.max_count_spin.setValue(history_settings.get("max_count", 50))
        self.auto_save_check.setChecked(history_settings.get("auto_save", True))
        self.update_history_count()
    
    def save_settings(self, settings):
        import utils
        # Save history settings
        current_history = utils.load_command_history()
        utils.save_command_history(current_history, self.max_count_spin.value())

class WindowsTab(QWidget):
    def __init__(self, parent_dialog=None):
        super().__init__()
        self.parent_dialog = parent_dialog
        layout = QVBoxLayout()
        
        # Theme settings
        theme_group = QGroupBox("Theme Settings")
        theme_layout = QFormLayout()

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["default", "dark", "light"])
        theme_layout.addRow("Theme:", self.theme_combo)

        theme_group.setLayout(theme_layout)
        layout.addWidget(theme_group)
        
        # Command Group settings
        command_group = QGroupBox("Command Group Settings")
        command_layout = QFormLayout()
        
        self.command_group_spin = QSpinBox()
        self.command_group_spin.setRange(3, 10)
        self.command_group_spin.setValue(3)  # default value
        command_layout.addRow("Number of Command Groups:", self.command_group_spin)
        
        # Description label
        info_label = QLabel("Set the number of command group buttons to display.\nRange: 3 to 10 buttons")
        info_label.setStyleSheet("color: #666; font-size: 11px;")
        command_layout.addRow(info_label)
        
        command_group.setLayout(command_layout)
        layout.addWidget(command_group)
        
        layout.addStretch()
        self.setLayout(layout)
    
    def load_settings(self, settings):
        # Load Theme setting
        self.theme_combo.setCurrentText(settings.get('theme', 'default'))
        
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
        self.font_tab = FontTab()
        self.output_tab = OutputTab()
        self.history_tab = HistoryTab()
        self.windows_tab = WindowsTab(self)  # Pass parent dialog reference
        
        # Add tabs
        self.tab_widget.addTab(self.font_tab, "Font")
        self.tab_widget.addTab(self.output_tab, "Output Window")
        self.tab_widget.addTab(self.history_tab, "History")
        self.tab_widget.addTab(self.windows_tab, "Windows")
        
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
        self.font_tab.load_settings(settings)
        self.output_tab.load_settings(settings)
        self.history_tab.load_settings(settings)
        self.windows_tab.load_settings(settings)
        
        return settings

    def save_settings(self):
        """Save settings to YAML file"""
        if not self.settings_path:
            return
        
        # Update settings from tabs
        self.font_tab.save_settings(self.settings)
        self.output_tab.save_settings(self.settings)
        self.history_tab.save_settings(self.settings)
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
            self.font_tab.save_settings(self.settings)
            self.output_tab.save_settings(self.settings)
            self.history_tab.save_settings(self.settings)
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