import sys
import os
import json
import re
import serial.tools.list_ports
import config

def get_resources(resource_file):
    if hasattr(sys, '_MEIPASS'):
        path = os.path.join(sys._MEIPASS, config.RESOURCES_DIR, resource_file)
    else:
        path = os.path.join(config.RESOURCES_DIR, resource_file)
    return path

def list_serial_ports():
    return [port.device for port in serial.tools.list_ports.comports()]

def load_comport_settings():
    settings_path = get_resources(config.SETTINGS_FILE_NAME)
    default_settings = {
        "comport_settings": {
            "port": "",
            "baudrate": 115200,
            "parity": "N",
            "stopbits": 1,
            "bytesize": 8,
            "timeout": 0.1
        }
    }
    if not os.path.exists(settings_path):
        try:
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(default_settings, f, indent=4)
            print(f"Default settings file created: {settings_path}")
        except Exception as e:
            print(f"Error creating default settings file: {e}")
            return default_settings
    try:
        with open(settings_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading comport settings from {settings_path}: {e}")
        return default_settings

def save_comport_settings(settings_data):
    settings_path = get_resources(config.SETTINGS_FILE_NAME)
    try:
        with open(settings_path, 'w', encoding='utf-8') as f:
            json.dump(settings_data, f, indent=4)
    except Exception as e:
        print(f"Error saving comport settings to {settings_path}: {e}")


def load_checkbox_lineedit_config(config_file_name=config.CONFIG_FILE):
    json_path = get_resources(config_file_name)
    default_data = []

    for i in range(10):
        default_data.append({
            "index": i,
            "checked": False,
            "title": {"text": "", "checked": False}
        })

    if not os.path.exists(json_path):
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(default_data, f, ensure_ascii=False, indent=2)
            print(f"Default checkbox/lineedit config created: {json_path}")
            return default_data
        except Exception as e:
            print(f"Error creating default checkbox/lineedit config: {e}")
            return default_data

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"JSON decode error in {json_path}. Creating default config.")
        os.remove(json_path)
        return load_checkbox_lineedit_config(config_file_name)
    except Exception as e:
        print(f"Error loading checkbox/lineedit config from {json_path}: {e}")
        return default_data

def save_checkbox_lineedit_config(data, config_file_name=config.CONFIG_FILE):
    json_path = get_resources(config_file_name)
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving checkbox/lineedit config to {json_path}: {e}")

def load_last_port_util():
    port_file = get_resources(config.PORT_SAVE_FILE_NAME)
    if os.path.exists(port_file):
        try:
            with open(port_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("selected_port", "")
        except json.JSONDecodeError:
            print(f"Error decoding JSON from {port_file}")
    return ""

def save_last_port_util(port):
    port_file = get_resources(config.PORT_SAVE_FILE_NAME)
    try:
        with open(port_file, 'w', encoding='utf-8') as f:
            json.dump({"selected_port": port}, f, indent=4)
    except Exception as e:
        print(f"Error saving last port to {port_file}: {e}")

def expand_ansi_tabs(text, tabsize=4):
    ansi_pattern = re.compile(r'(\x1b\[[0-9;]*m)')
    parts = ansi_pattern.split(text)
    result = []
    col = 0
    for part in parts:
        if ansi_pattern.match(part):
            result.append(part)
        else:
            for ch in part:
                if ch == '\t':
                    spaces = tabsize - (col % tabsize)
                    result.append(' ' * spaces)
                    col += spaces
                else:
                    result.append(ch)
                    if ch == '\n':
                        col = 0
                    else:
                        col += 1
    return ''.join(result)

def expand_ansi_cursor_right(text):
    def repl(match):
        n = int(match.group(1))
        return ' ' * n
    return re.sub(r'\x1b\[(\d+)C', repl, text)