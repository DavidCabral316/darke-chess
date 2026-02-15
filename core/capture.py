import mss
import numpy as np
import cv2

class ScreenCapture:
    def __init__(self):
        pass

    def capture(self, region):
        """
        Captures a screenshot of the specified region.
        :param region: Tuple (x, y, width, height) or dictionary with 'top', 'left', 'width', 'height'
        :return: Numpy array representing the image (BGR format for OpenCV)
        """
        # mss requires a dictionary for region: {'top': y, 'left': x, 'width': w, 'height': h}
        if isinstance(region, (tuple, list)):
            monitor = {
                "top": int(region[1]),
                "left": int(region[0]),
                "width": int(region[2]),
                "height": int(region[3])
            }
        else:
            monitor = region

        # Use context manager for thread safety (creates instance in current thread)
        with mss.mss() as sct:
            sct_img = sct.grab(monitor)
            
            # Convert to numpy array
            img = np.array(sct_img)
            
            # Convert BGRA to BGR
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            
            return img
