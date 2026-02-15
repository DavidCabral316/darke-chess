import ctypes
from PyQt6.QtWidgets import QWidget, QApplication, QRubberBand
from PyQt6.QtCore import Qt, QRect, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush

class OverlayWindow(QWidget):
    area_selected = pyqtSignal(QRect)

    def __init__(self):
        super().__init__()
        # Frameless, Always on Top, Tool Window (to hide from taskbar)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        
        # Initial geometry - covers the screen for area selection
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        
        self.begin = None
        self.end = None
        self.is_selecting = False
        self.best_move = None
        self.parent_rect = None
        
        self.rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self)
        
        # Force Topmost via Windows API
        self._ensure_topmost()

    def _ensure_topmost(self, click_through=True):
        """Forces the window to the absolute top and toggles click-through."""
        hwnd = int(self.winId())
        GWL_EXSTYLE = -20
        WS_EX_TOPMOST = 0x00000008
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_LAYERED = 0x00080000
        
        current_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        
        if click_through:
            new_style = current_style | WS_EX_TOPMOST | WS_EX_TRANSPARENT | WS_EX_LAYERED
        else:
            new_style = (current_style | WS_EX_TOPMOST | WS_EX_LAYERED) & ~WS_EX_TRANSPARENT
            
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
        
        # Set Pos to TopMost
        HWND_TOPMOST = -1
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_SHOWWINDOW = 0x0040
        ctypes.windll.user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)

    def clear(self):
        self.best_move = None
        self.update()

    def start_selection_mode(self):
        self.is_selecting = True
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self._ensure_topmost(click_through=False)
        self.setWindowOpacity(1.0)
        self.show()
        self.setCursor(Qt.CursorShape.CrossCursor)

    def draw_move(self, move_uci, board_rect, orientation='white'):
        self.is_selecting = False
        self.best_move = move_uci
        self.parent_rect = QRect(*board_rect)
        self.orientation = orientation
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._ensure_topmost(click_through=True)
        self.show()
        self.update()

    def mousePressEvent(self, event):
        if self.is_selecting:
            self.begin = event.pos()
            self.rubber_band.setGeometry(QRect(self.begin, self.begin))
            self.rubber_band.show()

    def mouseMoveEvent(self, event):
        if self.is_selecting and self.begin:
            self.rubber_band.setGeometry(QRect(self.begin, event.pos()).normalized())

    def mouseReleaseEvent(self, event):
        if self.is_selecting and self.begin:
            self.rubber_band.hide()
            rect = QRect(self.begin, event.pos()).normalized()
            # Map to global for the capture tool
            global_rect = QRect(self.mapToGlobal(rect.topLeft()), rect.size())
            self.area_selected.emit(global_rect)
            self.is_selecting = False
            self.hide()

    def _get_square_center(self, uci_sq):
        if not self.parent_rect: return None
        cols = {'a':0, 'b':1, 'c':2, 'd':3, 'e':4, 'f':5, 'g':6, 'h':7}
        c = cols[uci_sq[0]]
        r = int(uci_sq[1]) - 1
        
        if self.orientation == 'white':
            row, col = 7 - r, c
        else:
            row, col = r, 7 - c
            
        sq_w = self.parent_rect.width() / 8
        sq_h = self.parent_rect.height() / 8
        x = self.parent_rect.x() + (col * sq_w) + (sq_w / 2)
        y = self.parent_rect.y() + (row * sq_h) + (sq_h / 2)
        return int(x), int(y), int(sq_w), int(sq_h)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        if self.is_selecting:
            # Dim the screen during selection
            painter.fillRect(self.rect(), QColor(0, 0, 0, 80))
            return

        if self.best_move and self.parent_rect:
            # High Contrast Highlights
            src_info = self._get_square_center(self.best_move[:2])
            dst_info = self._get_square_center(self.best_move[2:4])
            
            if src_info and dst_info:
                # 1. From Square - Translucent Yellow with Orange border
                sx, sy, sw, sh = src_info
                painter.setPen(QPen(QColor(255, 140, 0, 255), 3))
                painter.setBrush(QBrush(QColor(255, 255, 0, 100)))
                painter.drawRect(int(sx - sw/2 + 5), int(sy - sh/2 + 5), int(sw - 10), int(sh - 10))
                
                # 2. To Square - Translucent Cyan with Blue border
                dx, dy, dw, dh = dst_info
                painter.setPen(QPen(QColor(0, 0, 255, 255), 3))
                painter.setBrush(QBrush(QColor(0, 255, 255, 100)))
                painter.drawRect(int(dx - dw/2 + 5), int(dy - dh/2 + 5), int(dw - 10), int(dh - 10))
                
                # 3. Arrow for direction
                painter.setPen(QPen(QColor(255, 255, 255, 200), 5))
                painter.drawLine(sx, sy, dx, dy)
