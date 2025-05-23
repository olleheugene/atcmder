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
