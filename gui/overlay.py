import ctypes
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

    def set_click_through(self, enable: bool):
        """
        Sets the window to be transparent to mouse events using Windows API.
        """
        hwnd = int(self.winId())
        GWL_EXSTYLE = -20
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_LAYERED = 0x00080000

        # Get current style
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        
        if enable:
            # Add Transparent and Layered flags
            style = style | WS_EX_TRANSPARENT | WS_EX_LAYERED
        else:
            # Remove Transparent flag
            style = style & ~WS_EX_TRANSPARENT
            
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)

    def set_capture_exclusion(self, enable: bool):
        """
        Excludes this window from screen capture (mss/OBS/etc) while keeping it visible to the user.
        Uses SetWindowDisplayAffinity (Windows 10+).
        """
        hwnd = int(self.winId())
        WDA_NONE = 0x00000000
        WDA_EXCLUDEFROMCAPTURE = 0x00000011 # Windows 10 version 2004+
        
        affinity = WDA_EXCLUDEFROMCAPTURE if enable else WDA_NONE
        try:
            ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, affinity)
        except Exception as e:
            print(f"Error setting display affinity: {e}")

    def clear(self):
        """Removes move markers from screen."""
        self.best_move = None
        self.update()

    def start_selection_mode(self):
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.set_capture_exclusion(False) # Ensure visible during selection
        self.show()
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.is_selecting = True
        self.update()

    def draw_move(self, move_uci, board_rect, orientation='white'):
        """
        Draws the best move on the overlay.
        """
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.best_move = move_uci
        self.parent_rect = QRect(*board_rect)
        self.orientation = orientation
        self.is_selecting = False
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.set_capture_exclusion(True) # Hide from mss
        self.show()
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
            global_rect = QRect(self.mapToGlobal(selection_rect.topLeft()), selection_rect.size())
            self.area_selected.emit(global_rect)
            self.is_selecting = False
            self.close()

    def get_square_rect(self, square_uci):
        if not self.best_move or not self.parent_rect:
            return QRect()
            
        col_map = {'a': 0, 'b': 1, 'c': 2, 'd': 3, 'e': 4, 'f': 5, 'g': 6, 'h': 7}
        file_idx = col_map[square_uci[0]]
        rank_idx = int(square_uci[1]) - 1
        
        if self.orientation == 'white':
            r = 7 - rank_idx
            c = file_idx
        else:
            r = rank_idx
            c = 7 - file_idx
            
        square_w = self.parent_rect.width() / 8
        square_h = self.parent_rect.height() / 8
        x = self.parent_rect.x() + (c * square_w)
        y = self.parent_rect.y() + (r * square_h)
        return QRect(int(x), int(y), int(square_w), int(square_h))

    def paintEvent(self, event):
        painter = QPainter(self)
        if self.is_selecting:
            painter.setBrush(QColor(0, 0, 0, 100))
            painter.drawRect(self.rect())
            if self.begin and self.end:
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
                painter.drawRect(QRect(self.begin, self.end).normalized())
        elif self.best_move and self.parent_rect:
            src = self.best_move[:2]
            dst = self.best_move[2:4]
            MARKER_H = 0.15 
            
            src_rect = self.get_square_rect(src)
            src_strip = QRect(src_rect.x(), src_rect.y() + int(src_rect.height() * (1.0 - MARKER_H)), 
                              src_rect.width(), int(src_rect.height() * MARKER_H))
            painter.setBrush(QColor(255, 255, 0, 200))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(src_strip)
            
            dst_rect = self.get_square_rect(dst)
            dst_strip = QRect(dst_rect.x(), dst_rect.y() + int(dst_rect.height() * (1.0 - MARKER_H)), 
                              dst_rect.width(), int(dst_rect.height() * MARKER_H))
            painter.setBrush(QColor(0, 255, 255, 200))
            painter.drawRect(dst_strip)
