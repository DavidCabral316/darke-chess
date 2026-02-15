import cv2
import numpy as np

class BoardVision:
    def __init__(self):
        self.templates = {} # Maps piece symbol (e.g. 'P', 'k') + square_color (0/1) -> image
        self.square_size = 0
        self.is_calibrated = False

    def split_board(self, image):
        """
        Splits the board image into 64 squares.
        :param image: Board image (BGR).
        :return: List of lists (8x8) containing square images.
        """
        h, w, _ = image.shape
        self.square_size = h // 8
        squares = []
        for r in range(8):
            row_squares = []
            for c in range(8):
                x = c * self.square_size
                y = r * self.square_size
                # Crop and maybe trim the edges slightly to avoid border noise
                sq = image[y:y+self.square_size, x:x+self.square_size]
                row_squares.append(sq)
            squares.append(row_squares)
        return squares

    def calibrate(self, image, orientation='white'):
        """
        Learns the piece templates from the starting position.
        :param image: Image of the board in starting position.
        :param orientation: 'white' (White at bottom) or 'black'.
        """
        squares = self.split_board(image)
        self.templates = {}
        
        # Standard starting position (from top-left)
        # White bottom: r n b q k b n r (row 0 - Black)
        # Black bottom: R N B K Q B N R (row 0 - White)
        
        if orientation == 'white':
            # Row 0: Black Pieces
            layout_0 = ['r', 'n', 'b', 'q', 'k', 'b', 'n', 'r']
            # Row 1: Black Pawns
            layout_1 = ['p'] * 8
            # Row 6: White Pawns
            layout_6 = ['P'] * 8
            # Row 7: White Pieces
            layout_7 = ['R', 'N', 'B', 'Q', 'K', 'B', 'N', 'R']
        else:
            # Row 0: White Pieces
            layout_0 = ['R', 'N', 'B', 'K', 'Q', 'B', 'N', 'R']
            # Row 1: White Pawns
            layout_1 = ['P'] * 8
            # Row 6: Black Pawns
            layout_6 = ['p'] * 8
            # Row 7: Black Pieces
            layout_7 = ['r', 'n', 'b', 'k', 'q', 'b', 'n', 'r']

        # Store templates
        # We need to distinguish between light and dark squares for the same piece
        # Square color parity: (row + col) % 2 == 0 -> Light (usually), 1 -> Dark
        # Note: Top-left (0,0) is usually LIGHT/WHITE in standard chess? 
        # Wait, "a1" is black. "a8" is white.
        # If board is standard: (0,0) is a8 -> White square. 
        # Let's use (r+c)%2 as key.
        
        def add_templates(row_idx, layout):
            for c, piece in enumerate(layout):
                sq_color = (row_idx + c) % 2
                self.templates[(piece, sq_color)] = squares[row_idx][c]

        add_templates(0, layout_0)
        add_templates(1, layout_1)
        add_templates(6, layout_6)
        add_templates(7, layout_7)
        
        # Also store Empty squares from central rows (rows 2, 3, 4, 5)
        # Just grab logic from row 3 (empty)
        # Layout: None
        for c in range(8):
            sq_color = (3 + c) % 2
            self.templates[('empty', sq_color)] = squares[3][c]
            
        self.is_calibrated = True
        print(f"Calibration complete. Templates stored: {len(self.templates)}")

    def get_board_state(self, image, orientation='white'):
        if not self.is_calibrated:
            return None
            
        squares = self.split_board(image)
        fen_rows = []
        
        for r in range(8):
            empty_count = 0
            row_str = ""
            for c in range(8):
                sq_img = squares[r][c]
                sq_color = (r + c) % 2
                
                best_match = None
                min_diff = float('inf')
                
                # Compare against all known templates for this square colors
                # Candidates: Empty + all pieces
                candidates = ['empty']
                candidates += ['r', 'n', 'b', 'q', 'k', 'p', 'R', 'N', 'B', 'Q', 'K', 'P']
                
                matched_symbol = None
                
                for sym in candidates:
                    key = (sym, sq_color)
                    if key in self.templates:
                        template = self.templates[key]
                        
                        # Resize if needed (should represent same size though)
                        if template.shape != sq_img.shape:
                            template = cv2.resize(template, (sq_img.shape[1], sq_img.shape[0]))
                            
                        # Simple SSD (Sum of Squared Differences)
                        diff = np.sum((sq_img.astype("float") - template.astype("float")) ** 2)
                        
                        if diff < min_diff:
                            min_diff = diff
                            matched_symbol = sym
                
                if matched_symbol == 'empty':
                    empty_count += 1
                else:
                    if empty_count > 0:
                        row_str += str(empty_count)
                        empty_count = 0
                    row_str += matched_symbol
            
            if empty_count > 0:
                row_str += str(empty_count)
            fen_rows.append(row_str)
            
        fen = "/".join(fen_rows)
        
        # Add metadata (active color, castling, etc. - simplified for now)
        # We assume it's White's turn if we are analyzing continuously, OR we need to detect turn.
        # For now, default to 'w' and full castling availability
        fen += " w KQkq - 0 1" 
        return fen
