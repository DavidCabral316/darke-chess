import sys
import cv2
import chess
import mss
import numpy
from PyQt6.QtWidgets import QApplication

# Test Engine
from core.engine import ChessEngine

def test_imports():
    print("Testing imports...")
    print(f"OpenCV: {cv2.__version__}")
    print(f"Chess: {chess.__version__}")
    print(f"Mss: {mss.__version__}")
    print(f"Numpy: {numpy.__version__}")
    print("PyQt6 imported successfully")

def test_engine():
    print("\nTesting Stockfish Engine...")
    try:
        engine = ChessEngine()
        engine.start()
        
        # Test analysis
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        move = engine.analyze(fen, time_limit=0.1)
        print(f"Engine suggested move: {move}")
        
        engine.stop()
        print("Engine test passed.")
    except Exception as e:
        print(f"Engine test failed: {e}")

if __name__ == "__main__":
    test_imports()
    test_engine()
