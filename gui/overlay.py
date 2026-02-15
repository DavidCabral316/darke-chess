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

    def start_selection_mode(self):
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.show()
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.is_selecting = True
        self.update()

    def draw_move(self, move_uci, board_rect, orientation='white'):
        """
        Draws the best move on the overlay.
        :param move_uci: Move in UCI format (e.g., "e2e4")
        :param board_rect: Tuple/list (x, y, w, h) of the board on screen
        :param orientation: 'white' or 'black'
        """
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.best_move = move_uci
        self.parent_rect = QRect(*board_rect) # Convert tuple to QRect
        self.orientation = orientation
        self.is_selecting = False
        self.setCursor(Qt.CursorShape.ArrowCursor)
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
            
            # Emit the selected area relative to the screen
            global_rect = QRect(self.mapToGlobal(selection_rect.topLeft()), selection_rect.size())
            
            self.area_selected.emit(global_rect)
            self.is_selecting = False
            self.close() # Hide after selection, BUT we need it open for drawing moves later.
            # We will re-open it or keep it open but transparent when analyzing.

    def get_square_rect(self, square_uci):
        """
        Calculates the QRect for a given square (e.g., 'e2') relative to the selection.
        """
        if not self.best_move or not self.parent_rect:
            return QRect()
            
        # self.parent_rect is the board geometry on screen (x, y, w, h)
        # But this window covers the WHOLE screen, so we can just use parent_rect coordinates directly.
        
        col_map = {'a': 0, 'b': 1, 'c': 2, 'd': 3, 'e': 4, 'f': 5, 'g': 6, 'h': 7}
        
        file_idx = col_map[square_uci[0]]
        rank_idx = int(square_uci[1]) - 1
        
        # Adjust for board orientation
        if self.orientation == 'white':
            # White bottom: a1 is (0, 7) in (col, row) if (0,0) is top-left
            # visual_row = 7 - rank_idx
            # visual_col = file_idx
            r = 7 - rank_idx
            c = file_idx
        else:
            # Black bottom: h8 is (0, 7)? No.
            # a1 is top-right? 
            # If Black is bottom, h1 is top-left? No, h8 is bottom-left?
            # Standard Black Bottom: 
            # Top-Left square is h1. Bottom-Right is a8.
            # Let's verify standard flip.
            # Normal: a8(0,0) ... h8(0,7)
            #         ...
            #         a1(7,0) ... h1(7,7)
            
            # Flipped: h1(0,0) ... a1(0,7)
            #          ...
            #          h8(7,0) ... a8(7,7)
            
            # So for a given file_idx (0-7, a-h) and rank_idx (0-7, 1-8):
            # r = rank_idx
            # c = 7 - file_idx
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
            painter.setBrush(QColor(0, 0, 0, 100)) # Semi-transparent black
            painter.drawRect(self.rect())
            
            # Clear the selected area
            if self.begin and self.end:
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
                painter.drawRect(QRect(self.begin, self.end).normalized())
        
        elif self.best_move and self.parent_rect:
            # Parse move (e.g. "e2e4")
            src = self.best_move[:2]
            dst = self.best_move[2:4]
            
            # Draw Source (Green-ish transparent)
            src_rect = self.get_square_rect(src)
            painter.setBrush(QColor(0, 255, 0, 100)) 
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(src_rect)
            
            # Draw Dest (Blue-ish transparent)
            dst_rect = self.get_square_rect(dst)
            painter.setBrush(QColor(0, 0, 255, 100))
            painter.drawRect(dst_rect)
