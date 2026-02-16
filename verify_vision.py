import cv2
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
    ok, msg = vision.calibrate(calib_img, orientation='white')
    if not ok:
        print(f"Calibration failed: {msg}")
        return
    
    # Verify start position stability
    start_fen = vision.get_board_state(calib_img, orientation='white')
    print(f"\nDetected Start FEN: {start_fen}")

    expected_start = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"
    if not start_fen:
        print("FAILURE: Vision returned None on calibration frame")
        return

    if start_fen.split()[0] == expected_start:
        print("SUCCESS: Start position detection is stable.")
    else:
        print("FAILURE: Start position detection mismatch.")

    # Optional diagnostic against a later frame (may be many moves later)
    later_fen = vision.get_board_state(test_img, orientation='white')
    print(f"Later frame FEN (diagnostic): {later_fen}")

if __name__ == "__main__":
    test_vision()
