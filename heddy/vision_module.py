import subprocess
import os
import base64
import uuid
import threading
import requests

from heddy.application_event import ApplicationEvent, ProcessingStatus

class VisionModule:
    def __init__(self, openai_api_key):
        self.api_key = openai_api_key
        self.capture_complete = threading.Event()

    def capture_image_async(self):
        """Initiates the image capture process in a new thread."""
        self.capture_complete.clear()  # Reset the event for the new capture process
        thread = threading.Thread(target=self.capture_image)
        thread.start()

    def capture_image(self):
        """Captures an image using fswebcam and saves it as a PNG file."""
        image_file_name = f"{uuid.uuid4()}.png"
        image_path = f"/tmp/{image_file_name}"
        print("Taking picture now...")
        capture_command = f"fswebcam --no-banner --resolution 1280x720 --save {image_path} -d /dev/video0 -r 1280x720 --png 1"

        try:
            subprocess.check_call(capture_command.split())
            self.capture_complete.set()  # Signal that the capture has completed
        except subprocess.CalledProcessError as e:
            print(f"Failed to capture image: {e}")
            image_path = None  # Ensure path is reset on failure
            self.capture_complete.set()  # Signal to unblock any waiting process, even though capture failed
        
        return image_path
    
    def handle_image_request(self, event: ApplicationEvent):
        image_path : str|None = self.capture_image()
        event.result = {
            "text": event.request,
            "image": image_path
        } 
        event.status = ProcessingStatus.SUCCESS if image_path is not None else ProcessingStatus.ERROR 
        return event



