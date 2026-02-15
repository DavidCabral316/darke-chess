from PyQt6.QtWidgets import QWidget, QApplication, QRubberBand
from PyQt6.QtCore import Qt, QRect, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen

class OverlayWindow(QWidget):
    area_selected = pyqtSignal(QRect)

    def __init__(self):
        super().__init__()
        # Make the window frameless, transparent, and always on top
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | 
                            Qt.WindowType.WindowStaysOnTopHint | 
                            Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        
        # Maximize to cover the whole screen for selection
        screen_geometry = QApplication.primaryScreen().geometry()
        self.setGeometry(screen_geometry)
        
        self.begin = None
        self.end = None
        self.is_selecting = False
        
        # Rubber band for selection visual
        self.rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self)

    def start_selection_mode(self):
        self.show()
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.is_selecting = True
        self.update()

    def mousePressEvent(self, event):
        if self.is_selecting:
            self.begin = event.pos()
            self.end = self.begin
            self.rubber_band.setGeometry(QRect(self.begin, self.end))
            self.rubber_band.show()

    def mouseMoveEvent(self, event):
        if self.is_selecting and self.begin:
            self.end = event.pos()
            self.rubber_band.setGeometry(QRect(self.begin, self.end).normalized())

    def mouseReleaseEvent(self, event):
        if self.is_selecting and self.begin:
            self.end = event.pos()
            self.rubber_band.hide()
            selection_rect = QRect(self.begin, self.end).normalized()
            
            # Emit the selected area relative to the screen
            # self.pos() is (0,0) usually, but good to be safe if multi-monitor (needs work)
            global_rect = QRect(self.mapToGlobal(selection_rect.topLeft()), selection_rect.size())
            
            self.area_selected.emit(global_rect)
            self.is_selecting = False
            self.close() # Hide the full screen overlay after selection

    def paintEvent(self, event):
        # We can add custom drawing here if needed, 
        # e.g., slightly dim the screen outside the selection
        if self.is_selecting:
            painter = QPainter(self)
            painter.setBrush(QColor(0, 0, 0, 100)) # Semi-transparent black
            painter.drawRect(self.rect())
            
            # Clear the selected area (make it fully transparent)
            if self.begin and self.end:
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
                painter.drawRect(QRect(self.begin, self.end).normalized())
