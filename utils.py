import sys
import os
import json
import re
import serial.tools.list_ports
import shutil

APP_ICON_NAME               = "app_icon.png"
CLEAR_ICON_NAME             = "clear.png"
LEFT_ARROW_ICON_NAME        = "left-3arrow.png"
RIGHT_ARROW_ICON_NAME       = "right-3arrow.png"
DEFAULT_CSS_NAME            = "default"
LIGHT_CSS_NAME              = "light"
DARK_CSS_NAME               = "dark"
RESOURCES_DIR               = "resources"

APP_VERSION                 = "1.3.0"
COMMAND_LIST_FILE           = "atcmder_user_cmdlist.json"
COMMANDS_PREDEFINED_FILE1   = "atcmder_predefined_cmd_1.json"
COMMANDS_PREDEFINED_FILE2   = "atcmder_predefined_cmd_2.json"
PORTS_FILE                  = "atcmder_ports.cfg"
SETTINGS_FILE               = "atcmder_settings.cfg"

def get_user_config_path(filename):
    if sys.platform.startswith("win"):
        config_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "atcmder")
    elif sys.platform == "darwin":
        config_dir = os.path.expanduser("~/Library/Application Support/atcmder")
    else:
        config_dir = os.path.expanduser("~/.atcmder")
    os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, filename)

USER_COMMAND_LIST           = get_user_config_path(COMMAND_LIST_FILE)
USER_PORT_LIST              = get_user_config_path(PORTS_FILE)
USER_SETTINGS               = get_user_config_path(SETTINGS_FILE)

PREDEFINED_COMMAND_LIST1    = get_user_config_path(COMMANDS_PREDEFINED_FILE1)
PREDEFINED_COMMAND_LIST2    = get_user_config_path(COMMANDS_PREDEFINED_FILE2)


def get_resources(resource_file):
    if hasattr(sys, '_MEIPASS'):
        path = os.path.join(sys._MEIPASS, RESOURCES_DIR, resource_file)
    else:
        path = os.path.join(RESOURCES_DIR, resource_file)
    # print(f"Resource path: {path}") # Uncomment for debugging
    return path

def list_serial_ports():
    return [port.device for port in serial.tools.list_ports.comports()]

def load_checkbox_lineedit_config(config_file_name=COMMAND_LIST_FILE):
    json_path = get_user_config_path(config_file_name)
    default_data = []
    # Default data generation logic (should be dynamically generated based on number of checkboxes, assuming 10 here for example)
    # In practice, should get UI element count from SerialTerminal class
    # Or it might be better to put part of this logic inside SerialTerminal class
    # Putting it in this function for simplification
    for i in range(10): # Example: 10 items
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
        return load_checkbox_lineedit_config(config_file_name) # Recursive call to generate defaults
    except Exception as e:
        print(f"Error loading checkbox/lineedit config from {json_path}: {e}")
        return default_data

def save_checkbox_lineedit_config(data, config_file_name=COMMAND_LIST_FILE):
    json_path = get_user_config_path(config_file_name)
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving checkbox/lineedit config to {json_path}: {e}")

def get_app_data_folder():
    """Return the path to the app's data folder (cross-platform)"""
    if sys.platform.startswith("win"):
        return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "atcmder")
    elif sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/atcmder")
    else:
        return os.path.expanduser("~/.atcmder")


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
    """
    Convert \x1b[{n}C sequences to n spaces
    """
    def repl(match):
        n = int(match.group(1))
        return ' ' * n
    return re.sub(r'\x1b\[(\d+)C', repl, text)

def is_ansi_sequence_complete(data):
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

def process_ansi_spacing(data: str) -> str:
    """Process only space-related ANSI control characters to implement proper spacing and alignment."""
    # Tab character (\t) processing - convert to 8 spaces
    data = data.replace('\t', '        ')
    
    # Vertical tab (\v) processing - convert to newline
    data = data.replace('\v', '\n')
    
    # Form feed (\f) processing - convert to newline
    data = data.replace('\f', '\n')
    
    # Normalize line break characters - unify Windows style (\r\n) to Unix style (\n)
    data = data.replace('\r\n', '\n')
    
    # Backspace character (\x08) processing
    while '\x08' in data:
        pos = data.find('\x08')
        if pos > 0:
            data = data[:pos-1] + data[pos+1:]
        else:
            data = data[1:]
    
    # Cursor forward movement (ESC[<n>C or ESC[<n>a) - convert to specified number of spaces
    data = re.sub(r'\x1b\[(\d+)?[Ca]', lambda m: ' ' * int(m.group(1) or 1), data)
    
    # Cursor backward movement (ESC[<n>D or ESC[<n>j) - remove
    data = re.sub(r'\x1b\[(\d+)?[Dj]', '', data)
    
    # Cursor horizontal absolute position (ESC[<n>G or ESC[<n>``) - move to line start then add spaces
    def handle_horizontal_position(match):
        pos = int(match.group(1) or 1) - 1  # Convert 1-based to 0-based
        return ' ' * pos if pos > 0 else ''
    data = re.sub(r'\x1b\[(\d+)?[G`]', handle_horizontal_position, data)
    
    # Move to horizontal tab stop (ESC[<n>I) - convert to spaces based on number of tabs
    data = re.sub(r'\x1b\[(\d+)?I', lambda m: ' ' * (8 * int(m.group(1) or 1)), data)
    
    # Reverse tab (ESC[<n>Z) - remove
    data = re.sub(r'\x1b\[(\d+)?Z', '', data)
    
    # Process ANSI space-related control sequences
    # Insert specified number of spaces (ICH - Insert Character, ESC[<n>@)
    data = re.sub(r'\x1b\[(\d+)?@', lambda m: ' ' * int(m.group(1) or 1), data)
    
    # Delete specified number of characters (DCH - Delete Character, ESC[<n>P) - remove
    data = re.sub(r'\x1b\[(\d+)?P', '', data)
    
    # Insert specified number of blank characters (ECH - Erase Character, ESC[<n>X)
    data = re.sub(r'\x1b\[(\d+)?X', lambda m: ' ' * int(m.group(1) or 1), data)
    
    # Line erase related (EL - Erase in Line)
    data = re.sub(r'\x1b\[0?K', '', data)  # Erase from cursor to end of line
    data = re.sub(r'\x1b\[1K', '', data)   # Erase from start of line to cursor
    data = re.sub(r'\x1b\[2K', '', data)   # Erase entire line
    
    # Screen erase related (ED - Erase in Display)
    data = re.sub(r'\x1b\[0?J', '', data)  # Erase from cursor to end of screen
    data = re.sub(r'\x1b\[1J', '', data)   # Erase from start of screen to cursor
    data = re.sub(r'\x1b\[2J', '', data)   # Erase entire screen
    data = re.sub(r'\x1b\[3J', '', data)   # Erase entire screen and scrollback buffer
    
    # Remove non-space-related ANSI cursor movement sequences (preserve color codes)
    data = re.sub(r'\x1b\[(\d+)?[AB]', '', data)  # Up/down movement
    data = re.sub(r'\x1b\[(\d+)?[EF]', '', data)  # Move to beginning of line
    data = re.sub(r'\x1b\[(\d+)?[LM]', '', data)  # Line insert/delete
    
    # Remove cursor position setting sequences (ESC[row;colH, ESC[row;colf)
    data = re.sub(r'\x1b\[\d+(;\d+)?[Hf]', '', data)
    
    # Convert space characters to actual spaces
    # Non-breaking space (NBSP, 0xA0)
    data = data.replace('\u00A0', ' ')
    
    # En space, Em space, Thin space etc.
    data = data.replace('\u2002', ' ')  # En space
    data = data.replace('\u2003', ' ')  # Em space
    data = data.replace('\u2004', ' ')  # Three-per-em space
    data = data.replace('\u2005', ' ')  # Four-per-em space
    data = data.replace('\u2006', ' ')  # Six-per-em space
    data = data.replace('\u2007', ' ')  # Figure space
    data = data.replace('\u2008', ' ')  # Punctuation space
    data = data.replace('\u2009', ' ')  # Thin space
    data = data.replace('\u200A', ' ')  # Hair space
    data = data.replace('\u202F', ' ')  # Narrow no-break space
    data = data.replace('\u205F', ' ')  # Medium mathematical space
    data = data.replace('\u3000', ' ')  # Ideographic space
    
    # Zero-width spaces processing (remove instead of converting to spaces)
    data = data.replace('\u200B', '')  # Zero-width space
    data = data.replace('\u200C', '')  # Zero-width non-joiner
    data = data.replace('\u200D', '')  # Zero-width joiner
    data = data.replace('\uFEFF', '')  # Zero-width no-break space (BOM)
    
    # Carriage return (\r) processing - overwrite current line without line break
    # But standalone \r is simply processed as move to line start
    if '\r' in data and '\r\n' not in data:
        lines = data.split('\n')
        processed_lines = []
        
        for line in lines:
            if line.endswith('\r'):
                # Remove \r at end of line (cursor position reset without line break)
                processed_line = line[:-1]
            elif '\r' in line:
                parts = line.split('\r')
                # Keep only the last part (overwrite effect)
                processed_line = parts[-1] if parts else ""
            else:
                processed_line = line
            processed_lines.append(processed_line)
        
        data = '\n'.join(processed_lines)
    
    return data

def prepare_default_files():
    if not os.path.exists(USER_COMMAND_LIST):
        shutil.copy(get_resources(COMMAND_LIST_FILE), USER_COMMAND_LIST)
    if not os.path.exists(USER_PORT_LIST):
        shutil.copy(get_resources(PORTS_FILE), USER_PORT_LIST)
    if not os.path.exists(USER_SETTINGS):
        shutil.copy(get_resources(SETTINGS_FILE), USER_SETTINGS)
    if not os.path.exists(PREDEFINED_COMMAND_LIST1):
        shutil.copy(get_resources(COMMANDS_PREDEFINED_FILE1), PREDEFINED_COMMAND_LIST1)
    if not os.path.exists(PREDEFINED_COMMAND_LIST2):
        shutil.copy(get_resources(COMMANDS_PREDEFINED_FILE2), PREDEFINED_COMMAND_LIST2)