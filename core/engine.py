import subprocess
import os
import threading
import queue
import time

class ChessEngine:
    """
    Thread-safe Stockfish wrapper using raw subprocess + UCI protocol.
    
    Uses a background reader thread to prevent readline() from blocking
    the analysis loop when the engine hangs or crashes.
    """
    
    def __init__(self, engine_path="stockfish/stockfish.exe"):
        if not os.path.exists(engine_path):
            raise FileNotFoundError(f"Stockfish engine not found at {engine_path}")
        
        self.engine_path = engine_path
        self.process = None
        self._lock = threading.Lock()
        self._output_queue = queue.Queue()
        self._reader_thread = None

    def start(self):
        """Starts the Stockfish engine process."""
        with self._lock:
            self._start_internal()
    
    def _start_internal(self):
        """Internal start (caller must hold lock)."""
        self._cleanup_process()
        
        try:
            self.process = subprocess.Popen(
                self.engine_path,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1
            )
            
            # Start background reader thread
            self._output_queue = queue.Queue()
            self._reader_thread = threading.Thread(
                target=self._reader_loop, daemon=True
            )
            self._reader_thread.start()
            
            # Initialize UCI
            self._send("uci")
            if not self._wait_for("uciok", timeout=5.0):
                print("Engine failed UCI init")
                self._cleanup_process()
                return
            
            self._send("isready")
            if not self._wait_for("readyok", timeout=5.0):
                print("Engine failed readyok")
                self._cleanup_process()
                return
                
            print("Stockfish engine started successfully.")
        except Exception as e:
            print(f"Failed to start engine: {e}")
            self._cleanup_process()

    def _cleanup_process(self):
        """Force-kill any existing process."""
        if self.process:
            try:
                self.process.kill()
                self.process.wait(timeout=2)
            except Exception:
                pass
        self.process = None

    def _reader_loop(self):
        """Background thread: reads stdout lines into a queue."""
        try:
            proc = self.process
            if proc is None:
                return
            while True:
                line = proc.stdout.readline()
                if not line:  # EOF = process died
                    self._output_queue.put(None)  # Sentinel
                    break
                self._output_queue.put(line.strip())
        except Exception:
            self._output_queue.put(None)  # Sentinel on error

    def stop(self):
        """Stops the engine process."""
        with self._lock:
            if self.process and self._is_alive():
                try:
                    self._send("quit")
                    self.process.wait(timeout=3)
                except Exception:
                    self._cleanup_process()
                print("Stockfish engine stopped.")
            self._cleanup_process()

    def _send(self, command):
        """Send a command to the engine."""
        if self.process and self._is_alive():
            try:
                self.process.stdin.write(command + "\n")
                self.process.stdin.flush()
            except (OSError, BrokenPipeError):
                pass

    def _read_line(self, timeout=5.0):
        """Read one line from the output queue with timeout. Returns None on timeout/EOF."""
        try:
            line = self._output_queue.get(timeout=timeout)
            return line  # None = EOF sentinel
        except queue.Empty:
            return None

    def _wait_for(self, token, timeout=5.0):
        """Read lines from engine until we see a line starting with token."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            line = self._read_line(timeout=remaining)
            if line is None:  # EOF or timeout
                return None
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
                
                # Drain any leftover output from previous commands
                while not self._output_queue.empty():
                    try:
                        self._output_queue.get_nowait()
                    except queue.Empty:
                        break
                
                # Set position and search
                self._send(f"position fen {fen}")
                self._send("isready")
                
                if not self._wait_for("readyok", timeout=3.0):
                    print("Engine not ready, restarting...")
                    self._cleanup_process()
                    return None
                
                time_ms = int(time_limit * 1000)
                self._send(f"go movetime {time_ms}")
                
                # Wait for bestmove with generous timeout
                timeout = time_limit + 5.0
                line = self._wait_for("bestmove", timeout=timeout)
                
                if line:
                    parts = line.split()
                    if len(parts) >= 2 and parts[1] != "(none)":
                        return parts[1]
                
                # If we got here, the engine timed out or died
                if not self._is_alive():
                    print("Engine died during analysis.")
                else:
                    print("Engine timed out during analysis.")
                    # Send stop and drain
                    self._send("stop")
                    self._wait_for("bestmove", timeout=2.0)
                
                return None
                
            except Exception as e:
                print(f"Analysis error: {e}")
                self._cleanup_process()
                return None
