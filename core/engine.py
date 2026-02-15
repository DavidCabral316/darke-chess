import subprocess
import os
import threading

class ChessEngine:
    """
    Thread-safe Stockfish wrapper using raw subprocess + UCI protocol.
    
    python-chess's SimpleEngine uses asyncio internally, which breaks when
    created in one thread and used in another (QThread). This implementation
    uses subprocess.Popen directly, making it fully thread-safe.
    """
    
    def __init__(self, engine_path="stockfish/stockfish.exe"):
        if not os.path.exists(engine_path):
            raise FileNotFoundError(f"Stockfish engine not found at {engine_path}")
        
        self.engine_path = engine_path
        self.process = None
        self._lock = threading.Lock()

    def start(self):
        """Starts the Stockfish engine process."""
        with self._lock:
            self._start_internal()
    
    def _start_internal(self):
        """Internal start (caller must hold lock)."""
        # Kill existing process if any
        if self.process and self.process.poll() is None:
            try:
                self.process.kill()
                self.process.wait(timeout=2)
            except Exception:
                pass
        
        try:
            self.process = subprocess.Popen(
                self.engine_path,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1
            )
            
            # Initialize UCI
            self._send("uci")
            self._wait_for("uciok")
            self._send("isready")
            self._wait_for("readyok")
            print("Stockfish engine started successfully.")
        except Exception as e:
            print(f"Failed to start engine: {e}")
            self.process = None

    def stop(self):
        """Stops the engine process."""
        with self._lock:
            if self.process and self.process.poll() is None:
                try:
                    self._send("quit")
                    self.process.wait(timeout=3)
                except Exception:
                    try:
                        self.process.kill()
                    except Exception:
                        pass
                print("Stockfish engine stopped.")
            self.process = None

    def _send(self, command):
        """Send a command to the engine."""
        if self.process and self.process.poll() is None:
            self.process.stdin.write(command + "\n")
            self.process.stdin.flush()

    def _wait_for(self, token, timeout=5.0):
        """Read lines from engine until we see a line starting with token."""
        import time
        start = time.time()
        while time.time() - start < timeout:
            if self.process is None or self.process.poll() is not None:
                return None
            line = self.process.stdout.readline().strip()
            if line.startswith(token):
                return line
        return None

    def _is_alive(self):
        """Check if the engine process is still running."""
        return self.process is not None and self.process.poll() is None

    def analyze(self, fen, time_limit=1.0, skill_level=None):
        """
        Analyzes the given FEN position.
        :param fen: FEN string of the position.
        :param time_limit: Time to analyze in seconds.
        :param skill_level: Optional skill level (0-20).
        :return: Best move string (e.g. "e2e4") or None.
        """
        with self._lock:
            # Auto-restart if engine is dead
            if not self._is_alive():
                print("Engine is not running. Restarting...")
                self._start_internal()
                if not self._is_alive():
                    return None

            try:
                # Set skill level if needed
                if skill_level is not None:
                    self._send(f"setoption name Skill Level value {skill_level}")
                
                # Set position and search
                self._send(f"position fen {fen}")
                self._send("isready")
                self._wait_for("readyok")
                
                time_ms = int(time_limit * 1000)
                self._send(f"go movetime {time_ms}")
                
                # Read until we get "bestmove"
                best_move = None
                import time
                start = time.time()
                timeout = time_limit + 5.0  # Extra buffer
                
                while time.time() - start < timeout:
                    if not self._is_alive():
                        print("Engine died during analysis.")
                        return None
                    
                    line = self.process.stdout.readline().strip()
                    
                    if line.startswith("bestmove"):
                        parts = line.split()
                        if len(parts) >= 2 and parts[1] != "(none)":
                            best_move = parts[1]
                        break
                
                return best_move
                
            except Exception as e:
                print(f"Analysis error: {e}")
                # Force restart on next call
                try:
                    self.process.kill()
                except Exception:
                    pass
                self.process = None
                return None
