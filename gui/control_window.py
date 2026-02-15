import sys
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QPushButton, 
                             QLabel, QComboBox, QCheckBox, QGroupBox, QMessageBox)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal

# Core Modules
from core.capture import ScreenCapture
from core.vision import BoardVision
from core.engine import ChessEngine

class AnalysisThread(QThread):
    fen_updated = pyqtSignal(str, str) # FEN, Best Move

    def __init__(self, capture, vision, engine):
        super().__init__()
        self.capture_tool = capture
        self.vision = vision
        self.engine = engine
        self.running = False
        self.region = None
        self.side = 'white'

    def run(self):
        self.running = True
        while self.running:
            if not self.region:
                break
            
            # 1. Capture Board
            frame = self.capture_tool.capture(self.region)
            
            # 2. Get FEN
            fen = self.vision.get_board_state(frame, self.side)
            
            # 3. Analyze
            if fen:
                best_move = self.engine.analyze(fen, time_limit=0.5)
                self.fen_updated.emit(fen, str(best_move))
            
            self.msleep(500) # Check every 500ms

    def stop(self):
        self.running = False
        self.wait()

class ControlWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Darke Chess - Control Panel")
        self.setGeometry(100, 100, 300, 500)
        
        # Tools
        self.capture_tool = ScreenCapture()
        self.vision = BoardVision()
        self.engine = ChessEngine()
        self.engine.start()
        
        # Overlay
        self.overlay = None
        self.selected_rect = None
        
        # Analysis Thread
        self.analysis_thread = AnalysisThread(self.capture_tool, self.vision, self.engine)
        self.analysis_thread.fen_updated.connect(self.update_info)

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Status Label
        self.status_label = QLabel("Status: Idle")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        # Controls Group
        controls_group = QGroupBox("Analysis Controls")
        controls_layout = QVBoxLayout()

        self.btn_select_area = QPushButton("Select Board Area")
        self.btn_calibrate = QPushButton("Calibrate (Start Pos)")
        self.btn_start = QPushButton("Start Analysis")
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setEnabled(False)
        self.btn_calibrate.setEnabled(False)

        controls_layout.addWidget(self.btn_select_area)
        controls_layout.addWidget(self.btn_calibrate)
        controls_layout.addWidget(self.btn_start)
        controls_layout.addWidget(self.btn_stop)
        controls_group.setLayout(controls_layout)
        layout.addWidget(controls_group)

        # Settings Group
        settings_group = QGroupBox("Engine Settings")
        settings_layout = QVBoxLayout()

        # Skill Level
        settings_layout.addWidget(QLabel("Skill Level (Elo):"))
        self.combo_skill = QComboBox()
        self.combo_skill.addItems(["Max (3000+)", "Grandmaster (2500)", "Master (2200)", "Club (1800)", "Beginner (1200)"])
        settings_layout.addWidget(self.combo_skill)

        # Human-like error
        self.check_human_errors = QCheckBox("Simulate Human Errors")
        self.check_human_errors.setChecked(True)
        settings_layout.addWidget(self.check_human_errors)

        # Side to Play
        settings_layout.addWidget(QLabel("Playing As (Orientation):"))
        self.combo_side = QComboBox()
        self.combo_side.addItems(["White (Bottom)", "Black (Bottom)"])
        settings_layout.addWidget(self.combo_side)
        
        # Display Info
        self.info_label = QLabel("FEN: N/A\nBest Move: N/A")
        self.info_label.setWordWrap(True)
        settings_layout.addWidget(self.info_label)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)
        
        self.setLayout(layout)

        # Connect signals
        self.btn_select_area.clicked.connect(self.select_area)
        self.btn_calibrate.clicked.connect(self.calibrate_board)
        self.btn_start.clicked.connect(self.start_analysis)
        self.btn_stop.clicked.connect(self.stop_analysis)

    def select_area(self):
        print("Select Area Clicked")
        self.status_label.setText("Status: Selecting Area...")
        
        from gui.overlay import OverlayWindow
        
        if self.overlay is None:
            self.overlay = OverlayWindow()
            self.overlay.area_selected.connect(self.on_area_selected)
            
        self.overlay.start_selection_mode()

    def on_area_selected(self, rect):
        self.selected_rect = (rect.x(), rect.y(), rect.width(), rect.height())
        self.status_label.setText(f"Area Selected: {rect.width()}x{rect.height()}")
        self.analysis_thread.region = self.selected_rect
        self.btn_calibrate.setEnabled(True)

    def calibrate_board(self):
        if not self.selected_rect:
            QMessageBox.warning(self, "Error", "Select board area first!")
            return
            
        self.status_label.setText("Status: Calibrating...")
        
        # Capture current frame
        frame = self.capture_tool.capture(self.selected_rect)
        
        # Determine orientation
        orientation_text = self.combo_side.currentText()
        orientation = 'white' if "White" in orientation_text else 'black'
        
        self.vision.calibrate(frame, orientation)
        self.status_label.setText("Status: Calibrated!")
        self.btn_start.setEnabled(True)

    def start_analysis(self):
        if not self.vision.is_calibrated:
            QMessageBox.warning(self, "Error", "Calibrate first!")
            return

        print("Start Analysis Clicked")
        self.status_label.setText("Status: Analyzing")
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.btn_calibrate.setEnabled(False)
        
        # Update thread settings
        orientation_text = self.combo_side.currentText()
        self.analysis_thread.side = 'white' if "White" in orientation_text else 'black'
        
        self.analysis_thread.start()

    def stop_analysis(self):
        print("Stop Clicked")
        self.status_label.setText("Status: Stopped")
        self.analysis_thread.stop()
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_calibrate.setEnabled(True)

    def update_info(self, fen, best_move):
        self.info_label.setText(f"FEN: {fen}\nBest Move: {best_move}")

    def closeEvent(self, event):
        self.analysis_thread.stop()
        self.engine.stop()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ControlWindow()
    window.show()
    sys.exit(app.exec())
