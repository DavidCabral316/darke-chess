import cv2
import numpy as np
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from core.vision import BoardVision

def test_vision():
    # Artifact paths
    artifact_dir = r"C:\Users\david\.gemini\antigravity\brain\05417ff8-efe9-4e6a-9cac-61de37fdb79c"
    calib_path = os.path.join(artifact_dir, "media__1771129225724.png")
    test_path = os.path.join(artifact_dir, "media__1771136809272.png")
    
    # Load images
    calib_img = cv2.imread(calib_path)
    test_img = cv2.imread(test_path)
    
    if calib_img is None or test_img is None:
        print(f"Error: Could not load images from {artifact_dir}")
        return

    print(f"Calibration image size: {calib_img.shape}")
    print(f"Test image size: {test_img.shape}")

    vision = BoardVision()
    
    # Calibrate
    vision.calibrate(calib_img, orientation='white')
    
    # Get board state
    fen = vision.get_board_state(test_img, orientation='white')
    print(f"\nDetected FEN: {fen}")
    
    expected = "r1bq1r1k/3nb1pp/p2p1p2/n2Pp3/PB2P3/1P3N1P/2B2PP1/RN1QR1K1"
    
    detected_part = fen.split()[0]
    print(f"Expected part: {expected}")
    
    if detected_part == expected:
        print("\nSUCCESS: Vision output matches expected FEN perfectly!")
    else:
        print("\nFAILURE: Vision output differs.")
        
        # Simple string expansion for comparison
        def expand(f):
            s = ""
            for char in f:
                if char.isdigit(): s += ' ' * int(char)
                elif char != '/': s += char
            return s
            
        s1 = expand(detected_part)
        s2 = expand(expected)
            
        diffs = [i for i, (a, b) in enumerate(zip(s1, s2)) if a != b]
        print(f"Number of differences: {len(diffs)}")
        files = 'abcdefgh'
        ranks = '87654321'
        for d in diffs:
            r = d // 8
            c = d % 8
            if d < len(s1) and d < len(s2):
                print(f"  Square {files[c]}{ranks[r]}: Seen '{s1[d]}' vs Expected '{s2[d]}'")

if __name__ == "__main__":
    test_vision()
