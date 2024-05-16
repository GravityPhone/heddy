import subprocess
import os
import uuid
import threading
import requests
import openai

class VisionModule:
    def __init__(self, openai_api_key):
        self.api_key = openai_api_key
        self.client = openai.OpenAI(api_key=self.api_key)
        self.capture_complete = threading.Event()
        self.image_path = None  # Add this to store the image path

    def capture_image_async(self):
        """Initiates the image capture process in a new thread."""
        self.capture_complete.clear()  # Reset the event for the new capture process
        thread = threading.Thread(target=self.capture_image)
        thread.start()

    def capture_image(self):
        """Captures an image using libcamera-still and saves it as a PNG file."""
        image_file_name = f"{uuid.uuid4()}.png"
        self.image_path = f"/tmp/{image_file_name}"
        print("Taking picture now...")
        capture_command = f"libcamera-still -o {self.image_path} --nopreview --timeout 1 --width 1280 --height 720"

        try:
            subprocess.check_call(capture_command.split())
            print(f"Image captured successfully: {self.image_path}")
            self.capture_complete.set()  # Signal that the capture has completed
        except subprocess.CalledProcessError as e:
            print(f"Failed to capture image: {e}")
            self.image_path = None  # Ensure path is reset on failure
            self.capture_complete.set()  # Signal to unblock any waiting process, even though capture failed

    def upload_image(self):
        if self.image_path and os.path.exists(self.image_path):
            file = self.client.files.create(
                file=open(self.image_path, "rb"),
                purpose="vision"
            )
            return file.id
        return None

