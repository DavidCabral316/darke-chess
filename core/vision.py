import cv2
import numpy as np
import chess


START_BOARD_PART = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"


class BoardVision:
    def __init__(self):
        self.is_calibrated = False
        self.square_size = 0
        self.cal_rect = (0, 0, 0, 0)
        self.bg_mean = {}
        self.bg_std = {}
        self.empty_edge_mean = 0.0
        self.empty_edge_std = 0.0
        self.empty_diff_mean = 0.0
        self.empty_diff_std = 0.0
        self.piece_brightness = {"white": [], "black": []}
        self.templates = {}
        self.type_templates = {}
        self.last_error = ""
        self.tracked_board = chess.Board()
        self.prev_signatures = None
        self.prev_occupancy = None
        self.prev_highlight_pair = None
        self.unresolved_change_frames = 0
        self.expected_player_move_uci = None

        self.start_piece_map = {
            (0, 0): "r",
            (0, 1): "n",
            (0, 2): "b",
            (0, 3): "q",
            (0, 4): "k",
            (0, 5): "b",
            (0, 6): "n",
            (0, 7): "r",
            (1, 0): "p",
            (1, 1): "p",
            (1, 2): "p",
            (1, 3): "p",
            (1, 4): "p",
            (1, 5): "p",
            (1, 6): "p",
            (1, 7): "p",
            (6, 0): "P",
            (6, 1): "P",
            (6, 2): "P",
            (6, 3): "P",
            (6, 4): "P",
            (6, 5): "P",
            (6, 6): "P",
            (6, 7): "P",
            (7, 0): "R",
            (7, 1): "N",
            (7, 2): "B",
            (7, 3): "Q",
            (7, 4): "K",
            (7, 5): "B",
            (7, 6): "N",
            (7, 7): "R",
        }

    def _reset(self):
        self.is_calibrated = False
        self.bg_mean = {}
        self.bg_std = {}
        self.piece_brightness = {"white": [], "black": []}
        self.templates = {}
        self.type_templates = {}
        self.last_error = ""
        self.tracked_board = chess.Board()
        self.prev_signatures = None
        self.prev_occupancy = None
        self.prev_highlight_pair = None
        self.unresolved_change_frames = 0
        self.expected_player_move_uci = None

    def set_expected_player_move(self, move_uci):
        self.expected_player_move_uci = move_uci

    def _normalize_board_rect(self, image, rect=None):
        if rect is None:
            x, y, w, h = 0, 0, image.shape[1], image.shape[0]
        else:
            x, y, w, h = rect

        side = int(min(w, h))
        x = int(x + (w - side) / 2)
        y = int(y + (h - side) / 2)

        trim = max(1, int(side * 0.01))
        x += trim
        y += trim
        side -= trim * 2

        x = max(0, x)
        y = max(0, y)
        side = min(side, image.shape[1] - x, image.shape[0] - y)
        return x, y, side, side

    def split_board(self, image, rect=None):
        x, y, bw, bh = self._normalize_board_rect(image, rect)
        self.square_size = int(min(bw, bh) / 8)

        xs = np.linspace(x, x + bw, 9).astype(int)
        ys = np.linspace(y, y + bh, 9).astype(int)
        squares = []
        for r in range(8):
            row = []
            for c in range(8):
                sx0, sx1 = xs[c], xs[c + 1]
                sy0, sy1 = ys[r], ys[r + 1]
                sq = image[sy0:sy1, sx0:sx1]
                row.append(sq)
            squares.append(row)
        return squares

    def _center_crop(self, img, margin=0.18):
        h, w = img.shape[:2]
        mx = int(w * margin)
        my = int(h * margin)
        return img[my : h - my, mx : w - mx]

    def _foreground_mask(self, sq_img, sq_color):
        if sq_color not in self.bg_mean:
            return np.zeros(sq_img.shape[:2], dtype=np.uint8)

        gray = cv2.cvtColor(sq_img, cv2.COLOR_BGR2GRAY)
        ref = self.bg_mean[sq_color]

        if ref.shape != gray.shape:
            ref = cv2.resize(ref, (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_LINEAR)

        diff = cv2.absdiff(gray, ref.astype(np.uint8))
        thr = max(12, int(np.mean(diff) + 1.2 * np.std(diff)))
        mask = (diff > thr).astype(np.uint8) * 255

        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        return mask

    def _occupancy_scores(self, sq_img, sq_color):
        center = self._center_crop(sq_img, margin=0.14)
        gray = cv2.cvtColor(center, cv2.COLOR_BGR2GRAY)
        mask = self._foreground_mask(center, sq_color)

        diff_ratio = float(np.mean(mask > 0))

        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 40, 110)
        edge_ratio = float(np.mean(edges > 0))
        return diff_ratio, edge_ratio, mask, gray

    def _piece_vector(self, gray, mask):
        ys, xs = np.where(mask > 0)
        if len(xs) < 12:
            return None

        x0, x1 = int(xs.min()), int(xs.max())
        y0, y1 = int(ys.min()), int(ys.max())
        pad = 2
        x0 = max(0, x0 - pad)
        y0 = max(0, y0 - pad)
        x1 = min(gray.shape[1] - 1, x1 + pad)
        y1 = min(gray.shape[0] - 1, y1 + pad)

        piece_mask = mask[y0 : y1 + 1, x0 : x1 + 1]
        if piece_mask.size == 0:
            return None

        resized = cv2.resize(piece_mask, (40, 40), interpolation=cv2.INTER_AREA)
        vec = resized.flatten().astype(np.float32)
        nrm = np.linalg.norm(vec)
        if nrm < 1e-6:
            return None
        return vec / nrm

    def _classify_color(self, gray, mask):
        fg = gray[mask > 0]
        if fg.size < 20:
            return "white"

        mean_fg = float(np.mean(fg))
        white_ref = np.mean(self.piece_brightness["white"]) if self.piece_brightness["white"] else 170.0
        black_ref = np.mean(self.piece_brightness["black"]) if self.piece_brightness["black"] else 90.0

        return "white" if abs(mean_fg - white_ref) <= abs(mean_fg - black_ref) else "black"

    def _classify_piece(self, vector, side_color):
        if vector is None:
            return None

        best_type = ""
        best_score = -1.0

        for ptype, vecs in self.type_templates.items():
            for tv in vecs:
                score = float(np.dot(vector, tv))
                if score > best_score:
                    best_score = score
                    best_type = ptype

        if best_score < 0.55:
            return None
        if not best_type:
            return None

        if side_color == "white":
            return best_type.upper()
        return best_type

    def _build_board_part(self, image):
        squares = self.split_board(image, rect=None)
        fen_rows = []

        for r in range(8):
            empties = 0
            row_fen = ""
            for c in range(8):
                sq = squares[r][c]
                sq_color = (r + c) % 2
                diff_ratio, edge_ratio, mask, gray = self._occupancy_scores(sq, sq_color)

                diff_threshold = self.empty_diff_mean + 2.0 * self.empty_diff_std
                edge_threshold = self.empty_edge_mean + 1.6 * self.empty_edge_std
                occupied = diff_ratio > max(0.02, diff_threshold) or edge_ratio > max(0.015, edge_threshold)

                if not occupied:
                    empties += 1
                    continue

                side_color = self._classify_color(gray, mask)
                vec = self._piece_vector(gray, mask)
                piece = self._classify_piece(vec, side_color)

                if piece is None:
                    empties += 1
                    continue

                if empties > 0:
                    row_fen += str(empties)
                    empties = 0
                row_fen += piece

            if empties > 0:
                row_fen += str(empties)
            fen_rows.append(row_fen)

        return "/".join(fen_rows)

    def _is_valid_board_part(self, board_part):
        rows = board_part.split("/")
        if len(rows) != 8:
            return False

        for row in rows:
            count = 0
            for ch in row:
                if ch.isdigit():
                    count += int(ch)
                elif ch in "prnbqkPRNBQK":
                    count += 1
                else:
                    return False
            if count != 8:
                return False

        if board_part.count("K") != 1 or board_part.count("k") != 1:
            return False
        return True

    def _is_start_position_by_occupancy(self, image):
        squares = self.split_board(image, rect=None)
        misses = 0

        for r in range(8):
            for c in range(8):
                sq = squares[r][c]
                sq_color = (r + c) % 2
                diff_ratio, edge_ratio, _, _ = self._occupancy_scores(sq, sq_color)

                diff_threshold = self.empty_diff_mean + 2.0 * self.empty_diff_std
                edge_threshold = self.empty_edge_mean + 1.6 * self.empty_edge_std
                occupied = diff_ratio > max(0.02, diff_threshold) or edge_ratio > max(0.015, edge_threshold)
                expected_occupied = (r, c) in self.start_piece_map

                if occupied != expected_occupied:
                    misses += 1

        return misses <= 2, misses

    def _square_signature(self, sq_img):
        center = self._center_crop(sq_img, margin=0.08)
        gray = cv2.cvtColor(center, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(gray, 55, 140)
        return cv2.resize(edges, (32, 32), interpolation=cv2.INTER_AREA)

    def _highlight_ratio(self, sq_img):
        center = self._center_crop(sq_img, margin=0.06)
        hsv = cv2.cvtColor(center, cv2.COLOR_BGR2HSV)

        # Chess.com move highlight (yellow/green tint)
        lower = np.array([20, 35, 70], dtype=np.uint8)
        upper = np.array([62, 255, 255], dtype=np.uint8)
        mask = cv2.inRange(hsv, lower, upper)
        return float(np.mean(mask > 0))

    def _occupancy_flag(self, diff_ratio, edge_ratio):
        diff_threshold = self.empty_diff_mean + 2.0 * self.empty_diff_std
        edge_threshold = self.empty_edge_mean + 1.6 * self.empty_edge_std
        return diff_ratio > max(0.02, diff_threshold) or edge_ratio > max(0.015, edge_threshold)

    def _collect_signatures(self, image):
        squares = self.split_board(image, rect=None)
        sigs = []
        occ = []
        highlights = []
        for r in range(8):
            for c in range(8):
                sq = squares[r][c]
                sigs.append(self._square_signature(sq))
                sq_color = (r + c) % 2
                diff_ratio, edge_ratio, _, _ = self._occupancy_scores(sq, sq_color)
                occ.append(self._occupancy_flag(diff_ratio, edge_ratio))
                highlights.append(self._highlight_ratio(sq))
        return sigs, occ, highlights

    def _detect_move_from_highlights(self, current_highlights, current_occupancy):
        prev_occ = self.prev_occupancy
        if prev_occ is None:
            return None, False

        indexed = sorted(enumerate(current_highlights), key=lambda x: x[1], reverse=True)
        if len(indexed) < 2:
            return None, False

        (idx1, val1), (idx2, val2) = indexed[0], indexed[1]
        strong = val1 > 0.12 and val2 > 0.12
        if not strong:
            return None, False

        highlight_pair = frozenset([idx1, idx2])
        if highlight_pair == self.prev_highlight_pair:
            return None, True

        candidates = []
        for mv in self.tracked_board.legal_moves:
            pair = frozenset([self._to_idx(mv.from_square), self._to_idx(mv.to_square)])
            if pair == highlight_pair:
                candidates.append(mv)

        if not candidates:
            return None, True

        best_move = None
        best_score = -999.0

        for mv in candidates:
            score = 0.0
            from_idx = self._to_idx(mv.from_square)
            to_idx = self._to_idx(mv.to_square)
            capture = self.tracked_board.piece_at(mv.to_square) is not None or self.tracked_board.is_en_passant(mv)

            if prev_occ[from_idx] and not current_occupancy[from_idx]:
                score += 2.0
            else:
                score -= 2.0

            if capture:
                if current_occupancy[to_idx]:
                    score += 2.0
                else:
                    score -= 2.0
            else:
                if (not prev_occ[to_idx]) and current_occupancy[to_idx]:
                    score += 2.0
                else:
                    score -= 2.0

            if score > best_score:
                best_score = score
                best_move = mv

        if best_score < 0.5:
            return None, True
        return best_move, True

    def _try_apply_expected_player_move(self, current_occupancy, current_highlights):
        if not self.expected_player_move_uci:
            return False
        if self.prev_occupancy is None:
            return False
        if not self.tracked_board.turn:
            return False

        try:
            mv = chess.Move.from_uci(self.expected_player_move_uci)
        except Exception:
            self.expected_player_move_uci = None
            return False

        if mv not in self.tracked_board.legal_moves:
            self.expected_player_move_uci = None
            return False

        from_idx = self._to_idx(mv.from_square)
        to_idx = self._to_idx(mv.to_square)
        capture = self.tracked_board.piece_at(mv.to_square) is not None or self.tracked_board.is_en_passant(mv)

        from_ok = self.prev_occupancy[from_idx] and not current_occupancy[from_idx]
        if capture:
            to_ok = current_occupancy[to_idx]
        else:
            to_ok = (not self.prev_occupancy[to_idx]) and current_occupancy[to_idx]

        indexed = sorted(enumerate(current_highlights), key=lambda x: x[1], reverse=True)
        highlight_ok = False
        if len(indexed) >= 2 and indexed[0][1] > 0.12 and indexed[1][1] > 0.12:
            pair = frozenset([indexed[0][0], indexed[1][0]])
            expected_pair = frozenset([from_idx, to_idx])
            highlight_ok = pair == expected_pair

        if (from_ok and to_ok) or highlight_ok:
            self.tracked_board.push(mv)
            self.expected_player_move_uci = None
            return True

        return False

    def _square_name(self, idx):
        file_idx = idx % 8
        row_idx = idx // 8
        rank = 8 - row_idx
        file_name = chr(ord("a") + file_idx)
        return f"{file_name}{rank}"

    def _expected_changed_squares(self, move, board_before):
        expected = {move.from_square, move.to_square}

        if board_before.is_castling(move):
            if chess.square_file(move.to_square) == 6:
                rook_from = chess.square(7, chess.square_rank(move.to_square))
                rook_to = chess.square(5, chess.square_rank(move.to_square))
            else:
                rook_from = chess.square(0, chess.square_rank(move.to_square))
                rook_to = chess.square(3, chess.square_rank(move.to_square))
            expected.update([rook_from, rook_to])

        if board_before.is_en_passant(move):
            direction = -1 if board_before.turn == chess.WHITE else 1
            captured = move.to_square + (8 * direction)
            expected.add(captured)

        return expected

    def _to_idx(self, sq):
        file_idx = chess.square_file(sq)
        rank_idx = chess.square_rank(sq)
        row = 7 - rank_idx
        return row * 8 + file_idx

    def _detect_move_from_signatures(self, current_signatures, current_occupancy):
        if self.prev_signatures is None or self.prev_occupancy is None:
            return None, False

        deltas = []
        for i, cur_sig in enumerate(current_signatures):
            prev_sig = self.prev_signatures[i]
            diff = float(np.mean(cv2.absdiff(cur_sig, prev_sig)))
            deltas.append(diff)

        changed = {i for i, d in enumerate(deltas) if d > 12.0}
        if len(changed) < 2:
            return None, False

        best_move = None
        best_score = -999.0

        for mv in self.tracked_board.legal_moves:
            expected_sq = self._expected_changed_squares(mv, self.tracked_board)
            expected_idx = {self._to_idx(sq) for sq in expected_sq}

            overlap = len(expected_idx & changed)
            missing = len(expected_idx - changed)
            extra = len(changed - expected_idx)
            score = overlap * 3.5 - missing * 2.5 - extra * 0.6

            from_idx = self._to_idx(mv.from_square)
            to_idx = self._to_idx(mv.to_square)
            from_transition_ok = self.prev_occupancy[from_idx] and not current_occupancy[from_idx]
            capture = self.tracked_board.piece_at(mv.to_square) is not None or self.tracked_board.is_en_passant(mv)

            if from_transition_ok:
                score += 2.0
            else:
                score -= 2.0

            if capture:
                if current_occupancy[to_idx]:
                    score += 2.0
                else:
                    score -= 3.0
            else:
                if (not self.prev_occupancy[to_idx]) and current_occupancy[to_idx]:
                    score += 2.0
                else:
                    score -= 2.0

            if score > best_score:
                best_score = score
                best_move = mv

        if best_move is None:
            return None, True

        expected = {self._to_idx(sq) for sq in self._expected_changed_squares(best_move, self.tracked_board)}
        overlap = len(expected & changed)

        if overlap < 2 or best_score < 3.0:
            return None, True

        return best_move, True

    def calibrate(self, image, orientation="white"):
        self._reset()
        if orientation != "white":
            self.last_error = "Current calibration mode only supports white at bottom."
            return False, self.last_error

        self.cal_rect = self._normalize_board_rect(image)
        squares = self.split_board(image, rect=self.cal_rect)

        bg_samples = {0: [], 1: []}
        empty_diff_scores = []
        empty_edge_scores = []

        for r in range(8):
            for c in range(8):
                sq = squares[r][c]
                sq_color = (r + c) % 2
                center = self._center_crop(sq, margin=0.14)
                gray = cv2.cvtColor(center, cv2.COLOR_BGR2GRAY)
                gray_ref = cv2.resize(gray, (48, 48), interpolation=cv2.INTER_AREA)

                if (r, c) not in self.start_piece_map:
                    bg_samples[sq_color].append(gray_ref)

        for color in (0, 1):
            if not bg_samples[color]:
                self.last_error = "Could not sample empty squares for calibration."
                return False, self.last_error

            stacked = np.stack(bg_samples[color], axis=0).astype(np.float32)
            self.bg_mean[color] = np.mean(stacked, axis=0)
            self.bg_std[color] = np.std(stacked, axis=0)

        for r in range(8):
            for c in range(8):
                sq = squares[r][c]
                sq_color = (r + c) % 2
                diff_ratio, edge_ratio, mask, gray = self._occupancy_scores(sq, sq_color)

                if (r, c) in self.start_piece_map:
                    sym = self.start_piece_map[(r, c)]
                    self.templates.setdefault(sym, [])
                    self.type_templates.setdefault(sym.lower(), [])

                    vec = self._piece_vector(gray, mask)
                    if vec is not None:
                        self.templates[sym].append(vec)
                        self.type_templates[sym.lower()].append(vec)

                    fg = gray[mask > 0]
                    if fg.size > 20:
                        side = "white" if sym.isupper() else "black"
                        self.piece_brightness[side].append(float(np.mean(fg)))
                else:
                    empty_diff_scores.append(diff_ratio)
                    empty_edge_scores.append(edge_ratio)

        if not empty_diff_scores or not empty_edge_scores:
            self.last_error = "Calibration failed: empty square statistics unavailable."
            return False, self.last_error

        self.empty_diff_mean = float(np.mean(empty_diff_scores))
        self.empty_diff_std = float(np.std(empty_diff_scores) + 1e-6)
        self.empty_edge_mean = float(np.mean(empty_edge_scores))
        self.empty_edge_std = float(np.std(empty_edge_scores) + 1e-6)

        missing_templates = [sym for sym in set(self.start_piece_map.values()) if sym not in self.templates]
        if missing_templates:
            self.last_error = f"Calibration failed: missing templates for {missing_templates}."
            return False, self.last_error

        is_start, misses = self._is_start_position_by_occupancy(image)
        if not is_start:
            self.last_error = (
                "Calibration must be done in the exact start position. "
                f"Detected occupancy mismatches: {misses} squares."
            )
            return False, self.last_error

        self.is_calibrated = True
        self.tracked_board = chess.Board()
        self.prev_signatures, self.prev_occupancy, _ = self._collect_signatures(image)
        self.prev_highlight_pair = None
        self.expected_player_move_uci = None
        self.last_error = ""
        print("Calibration complete and validated (start position confirmed).")
        return True, "Calibration complete."

    def get_board_state(self, image, orientation="white"):
        if not self.is_calibrated:
            return None
        if orientation != "white":
            return None

        current_signatures, current_occupancy, current_highlights = self._collect_signatures(image)

        if self._try_apply_expected_player_move(current_occupancy, current_highlights):
            self.prev_signatures = current_signatures
            self.prev_occupancy = current_occupancy

        move, used_highlight = self._detect_move_from_highlights(current_highlights, current_occupancy)
        had_change = used_highlight
        if move is None:
            move2, had_change2 = self._detect_move_from_signatures(current_signatures, current_occupancy)
            if move2 is not None:
                move = move2
                had_change = had_change2
            else:
                had_change = had_change or had_change2

        if move is not None:
            try:
                self.tracked_board.push(move)
                self.unresolved_change_frames = 0
            except Exception:
                pass
            self.prev_signatures = current_signatures
            self.prev_occupancy = current_occupancy
            if used_highlight:
                self.prev_highlight_pair = frozenset([
                    self._to_idx(move.from_square),
                    self._to_idx(move.to_square),
                ])
        elif had_change:
            self.unresolved_change_frames += 1
            if self.unresolved_change_frames >= 5:
                self.prev_signatures = current_signatures
                self.prev_occupancy = current_occupancy
                self.unresolved_change_frames = 0
        else:
            self.unresolved_change_frames = 0
            self.prev_signatures = current_signatures
            self.prev_occupancy = current_occupancy

            indexed = sorted(enumerate(current_highlights), key=lambda x: x[1], reverse=True)
            if len(indexed) >= 2 and indexed[0][1] > 0.20 and indexed[1][1] > 0.20:
                self.prev_highlight_pair = frozenset([indexed[0][0], indexed[1][0]])
            else:
                self.prev_highlight_pair = None

        return self.tracked_board.fen()
