import sys
from PySide6.QtWidgets import QApplication
from serial_terminal import SerialTerminal

def main():
    app = QApplication(sys.argv)
    window = SerialTerminal()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
