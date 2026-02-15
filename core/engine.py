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
            try:
                self.engine.quit()
            except (chess.engine.EngineTerminatedError, Exception):
                pass # Already dead
            self.engine = None
            print("Stockfish engine stopped.")

    def analyze(self, fen, time_limit=1.0, skill_level=None):
        """
        Analyzes the given FEN position.
        :param fen: FEN string of the position.
        :param time_limit: Time to analyze in seconds.
        :param skill_level: Optional skill level (0-20).
        :return: Best move (chess.Move) or None.
        """
        # Auto-restart if engine is dead or None
        if not self.engine or self.engine.returncode is not None:
            print("Engine is not running or crashed. Restarting...")
            self.start()
            if not self.engine:
                return None

        board = chess.Board(fen)
        
        # Configure skill level only if needed
        if skill_level is not None:
            try:
                self.engine.configure({"Skill Level": skill_level})
            except Exception as e:
                print(f"Failed to set skill level: {e}")

        try:
            result = self.engine.play(board, chess.engine.Limit(time=time_limit))
            return result.move
        except (chess.engine.EngineTerminatedError, Exception):
            print("Engine crashed during analysis. Attempting to restart...")
            # If it crashed, self.engine might be in a bad state. Force cleanup.
            self.engine = None 
            self.start()
            
            # Retry once
            if self.engine:
                try:
                    result = self.engine.play(board, chess.engine.Limit(time=time_limit))
                    return result.move
                except Exception as e:
                    print(f"Retry failed: {e}")
            return None
