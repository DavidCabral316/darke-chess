import sys
from PyQt6.QtWidgets import QApplication
from gui.control_window import ControlWindow

def main():
    app = QApplication(sys.argv)
    window = ControlWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
