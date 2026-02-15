import chess
import chess.engine
import os

class ChessEngine:
    def __init__(self, engine_path="stockfish/stockfish.exe"):
        if not os.path.exists(engine_path):
            raise FileNotFoundError(f"Stockfish engine not found at {engine_path}")
        
        self.engine_path = engine_path
        self.engine = None

    def start(self):
        """Starts the Stockfish engine process."""
        try:
            self.engine = chess.engine.SimpleEngine.popen_uci(self.engine_path)
            print("Stockfish engine started successfully.")
        except Exception as e:
            print(f"Failed to start engine: {e}")
            self.engine = None

    def stop(self):
        """Stops the engine process."""
        if self.engine:
            self.engine.quit()
            self.engine = None
            print("Stockfish engine stopped.")

    def analyze(self, fen, time_limit=1.0, skill_level=None):
        """
        Analyzes the given FEN position.
        :param fen: FEN string of the position.
        :param time_limit: Time to analyze in seconds.
        :param skill_level: Optional skill level (0-20) or specific Elo.
        :return: Best move (chess.Move) or None.
        """
        if not self.engine:
            print("Engine is not running. Call start() first.")
            return None

        board = chess.Board(fen)
        
        # Configure skill level if provided
        if skill_level is not None:
             # Stockfish supports Skill Level from 0 to 20
             # We can map Elo to this if needed, but for now let's assume raw skill level 0-20
             self.engine.configure({"Skill Level": skill_level})

        try:
            result = self.engine.play(board, chess.engine.Limit(time=time_limit))
            return result.move
        except Exception as e:
            print(f"Analysis error: {e}")
            return None
