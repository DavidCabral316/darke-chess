import cv2
import numpy as np
from skimage.feature import hog

class BoardVision:
    def __init__(self):
        self.templates = {} # (symbol, sq_color) -> HOG feat
        self.bg_stats = {}  # sq_color -> (mean_img, std_img)
        self.sq_medians = {} # (r, c) -> baseline intensity
        self.is_calibrated = False
        self.square_size = 0
        self.cal_rect = (0, 0, 0, 0)
        
        # HOG Parameters optimized for chess pieces
        self.hog_params = {
            'orientations': 9,
            'pixels_per_cell': (8, 8),
            'cells_per_block': (2, 2),
            'visualize': False,
        }

    def _get_board_rect(self, image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 40, 100)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        h, w = gray.shape
        best_rect = (0, 0, w, h)
        if contours:
            max_area = 0
            for cnt in contours:
                x, y, cw, ch = cv2.boundingRect(cnt)
                area = cw * ch
                if 0.9 <= (cw / ch) <= 1.1 and area > (h * w * 0.4):
                    if area > max_area:
                        max_area, best_rect = area, (x, y, cw, ch)
        return best_rect

    def split_board(self, image, rect=None):
        x, y, bw, bh = rect if rect else self._get_board_rect(image)
        self.square_size = bw // 8
        squares = []
        for r in range(8):
            row = []
            for c in range(8):
                sx, sy = x + c * self.square_size, y + r * self.square_size
                sq = image[sy:sy+self.square_size, sx:sx+self.square_size]
                row.append(sq)
            squares.append(row)
        return squares

    def _extract_features(self, sq_img, mask=None):
        if sq_img.size == 0: return None
        gray = cv2.cvtColor(sq_img, cv2.COLOR_BGR2GRAY)
        
        if mask is not None:
            gray = cv2.bitwise_and(gray, gray, mask=mask)
            
        resized = cv2.resize(gray, (64, 64))
        fd = hog(resized, **self.hog_params)
        return {'hog': fd}

    def _get_hollow_filled_mask(self, mask):
        """Fills holes in the mask to handle white pieces on white squares."""
        if mask is None: return None
        # Closing operation to bridge small gaps
        kernel = np.ones((5,5), np.uint8)
        mask_closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        
        # Contour filling (Flood fill holes)
        mask_filled = mask_closed.copy()
        h, w = mask_filled.shape
        # Create a mask for floodFill (size + 2)
        ff_mask = np.zeros((h+2, w+2), np.uint8)
        cv2.floodFill(mask_filled, ff_mask, (0,0), 255)
        mask_inv = cv2.bitwise_not(mask_filled)
        out = mask_closed | mask_inv
        return out

    def _get_differential_mask(self, sq_img, sq_color):
        if sq_color not in self.bg_stats: return None
        mean_img, std_img = self.bg_stats[sq_color]
        gray = cv2.cvtColor(sq_img, cv2.COLOR_BGR2GRAY)
        
        diff = np.abs(gray.astype(np.float32) - mean_img)
        # Use a balanced threshold for wood
        mask = (diff > (std_img * 4.2 + 12.0)).astype(np.uint8) * 255
        
        # Morphological cleanup
        kernel = np.ones((3,3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        return mask

    def calibrate(self, image, orientation='white'):
        self.cal_rect = self._get_board_rect(image)
        squares = self.split_board(image, rect=self.cal_rect)
        self.templates = {}
        self.bg_stats = {}
        self.sq_medians = {}
        
        piece_map = {
            (0,0): 'r', (0,1): 'n', (0,2): 'b', (0,3): 'q', (0,4): 'k', (0,5): 'b', (0,6): 'n', (0,7): 'r',
            (1,0): 'p', (1,1): 'p', (1,2): 'p', (1,3): 'p', (1,4): 'p', (1,5): 'p', (1,6): 'p', (1,7): 'p',
            (6,0): 'P', (6,1): 'P', (6,2): 'P', (6,3): 'P', (6,4): 'P', (6,5): 'P', (6,6): 'P', (6,7): 'P',
            (7,0): 'R', (7,1): 'N', (7,2): 'B', (7,3): 'Q', (7,4): 'K', (7,5): 'B', (7,6): 'N', (7,7): 'R'
        }

        # 1. Background Stats & Medians
        bg_samples = {0: [], 1: []}
        for r in range(8):
            for c in range(8):
                gray_sq = cv2.cvtColor(squares[r][c], cv2.COLOR_BGR2GRAY)
                self.sq_medians[(r, c)] = np.median(gray_sq)
                
                if (r, c) not in piece_map:
                    sq_color = (r + c) % 2
                    bg_samples[sq_color].append(gray_sq)
        
        for color, samples in bg_samples.items():
            if samples:
                stacked = np.stack(samples, axis=0).astype(np.float32)
                self.bg_stats[color] = (np.mean(stacked, axis=0), np.std(stacked, axis=0))

        # 2. Piece Templates
        for loc, sym in piece_map.items():
            r, c = loc
            sq = squares[r][c]
            sq_color = (r + c) % 2
            mask = self._get_differential_mask(sq, sq_color)
            mask = self._get_hollow_filled_mask(mask)
            feat = self._extract_features(sq, mask=mask)
            self.templates[(sym, sq_color)] = feat

        self.is_calibrated = True
        print(f"Calibration v7 Complete (Comparative Intensity).")

    def get_board_state(self, image, orientation='white'):
        if not self.is_calibrated: return None
        squares = self.split_board(image, rect=self.cal_rect)
        
        fen_rows = []
        for r in range(8):
            empty_count = 0
            row_str = ""
            for c in range(8):
                sq = squares[r][c]
                gray = cv2.cvtColor(sq, cv2.COLOR_BGR2GRAY)
                sq_color = (r + c) % 2
                
                # 1. Extract Mask & Fill Hollows
                mask = self._get_differential_mask(sq, sq_color)
                mask = self._get_hollow_filled_mask(mask)
                
                fg_size = np.sum(mask > 0)
                fg_ratio = fg_size / mask.size
                
                # Pruning: Wood texture rarely produces solid masks > 8%
                if fg_ratio < 0.08:
                    empty_count += 1
                else:
                    # 2. Comparative Polarity: Piece vs Calibrated Background
                    piece_med = np.median(gray[mask > 0])
                    ref_med = self.sq_medians[(r, c)]
                    
                    # White pieces are significantly lighter than their empty square background
                    # Black pieces are significantly darker.
                    is_bright = piece_med > ref_med
                    
                    feat = self._extract_features(sq, mask=mask)
                    best_match = None
                    max_sim = -1.0
                    
                    candidates = ['r', 'n', 'b', 'q', 'k', 'p', 'R', 'N', 'B', 'Q', 'K', 'P']
                    for sym in candidates:
                        key = (sym, sq_color)
                        if key in self.templates:
                            t = self.templates[key]
                            # Similarity check
                            sim = np.dot(feat['hog'], t['hog']) / (np.linalg.norm(feat['hog']) * np.linalg.norm(t['hog']) + 1e-9)
                            
                            # Color Polarity
                            t_is_white = sym.isupper()
                            polarity_score = 1.0 if t_is_white == is_bright else 0.1
                            
                            final_score = sim * 0.6 + polarity_score * 0.4
                            
                            if final_score > max_sim:
                                max_sim = final_score
                                best_match = sym
                    
                    if max_sim > 0.35:
                        if empty_count > 0:
                            row_str += str(empty_count)
                            empty_count = 0
                        row_str += best_match
                    else:
                        empty_count += 1
            
            if empty_count > 0:
                row_str += str(empty_count)
            fen_rows.append(row_str)
            
        return "/".join(fen_rows) + " w KQkq - 0 1"
