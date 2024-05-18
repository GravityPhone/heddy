import base64
import os

def encode_image_to_base64(image_path):
    """Encodes the captured image to a base64 string."""
    if image_path and os.path.exists(image_path):
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    else:
        print("No image file found or image capture failed.")
    return None