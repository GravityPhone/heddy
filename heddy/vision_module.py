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
        """Captures an image using libcamera-still and saves it as a PNG file."""
        image_file_name = f"{uuid.uuid4()}.png"
        image_path = f"/tmp/{image_file_name}"
        print("Taking picture now...")
        capture_command = f"libcamera-still -o {image_path} --nopreview --timeout 1 --width 1280 --height 720"

        try:
            print(f"Running command: {capture_command}")
            output = subprocess.check_output(capture_command.split(), stderr=subprocess.STDOUT)
            print(f"Image captured successfully: {image_path}")
            print(f"Command output: {output.decode().strip()}")
            self.capture_complete.set()  # Signal that the capture has completed
        except subprocess.CalledProcessError as e:
            print(f"Failed to capture image: {e}")
            print(f"Command output: {e.output.decode().strip()}")
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



