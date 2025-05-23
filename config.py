import os
import sys
import shutil
import logging

APP_VERSION = "v0.7"
COMMAND_LIST_FILE = "atcmder_cmdlist.json"
RECENT_PORTS_FILE = "atcmder_recent_ports.json"

# Logging setup (optional, can be expanded)
log_dir = os.path.expanduser("~/.atcmder/logs")
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(log_dir, "atcmder.log"),
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)

def get_resources(resource_file):
    if hasattr(sys, '_MEIPASS'):
        path = os.path.join(sys._MEIPASS, "resources", resource_file)
    else:
        path = os.path.join("resources", resource_file)
    return path

def get_user_config_path(filename):
    if sys.platform.startswith("win"):
        config_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "atcmder")
    elif sys.platform == "darwin":
        config_dir = os.path.expanduser("~/Library/Application Support/atcmder")
    else:
        config_dir = os.path.expanduser("~/.atcmder")
    os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, filename)

USER_COMMAND_LIST = get_user_config_path(COMMAND_LIST_FILE)
USER_PORT_LIST = get_user_config_path(RECENT_PORTS_FILE)

def safe_copy(src, dst):
    if not os.path.exists(dst):
        try:
            shutil.copy(src, dst)
        except Exception as e:
            logging.warning(f"Copy failed: {src} -> {dst}: {e}")

# Ensure user config files exist
if not os.path.exists(USER_COMMAND_LIST):
    safe_copy(get_resources(COMMAND_LIST_FILE), USER_COMMAND_LIST)
if not os.path.exists(USER_PORT_LIST):
    safe_copy(get_resources(RECENT_PORTS_FILE), USER_PORT_LIST)

CONFIG_FILE = "atcmder_config.json"
PORT_SAVE_FILE_NAME = "atcmder_last_port.json" # PORT_SAVE_FILE 대신 사용
SETTINGS_FILE_NAME = "atcmd_settings.json"
APP_ICON_NAME = "app_icon.png"
CLEAR_ICON_NAME = "clear.png"
LEFT_ARROW_ICON_NAME = "left-3arrow.png"
RIGHT_ARROW_ICON_NAME = "right-3arrow.png"
DEFAULT_CSS_NAME = "default.css"
LIGHT_CSS_NAME = "light.css"
DARK_CSS_NAME = "dark.css"
RESOURCES_DIR = "resources"