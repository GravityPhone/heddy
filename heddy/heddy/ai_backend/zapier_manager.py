from heddy.application_event import ApplicationEvent, ProcessingStatus, ApplicationEventType
import json
import requests

def tool_call_zapier(arguments):
    webhook_url = "https://hooks.zapier.com/hooks/catch/82343/19816978ac224264aa3eec6c8c911e10/"
    
    # Parse the arguments as JSON if it's a string
    if isinstance(arguments, str):
        arguments = json.loads(arguments)
    
    # Access the 'message' key instead of 'text'
    text_to_send = arguments.get('message', '')  # Default to empty string if 'message' not found
    
    payload = {"text": text_to_send}
    response = requests.post(webhook_url, json=payload)
    if response.status_code == 200:
        return "Success!"
    else:
        raise RuntimeError(f"Failed with {response.status_code=}")
    
class ZapierManager:
    def handle_message(self, event: ApplicationEvent):
        try:
            event.result = tool_call_zapier(event.request)
            event.status = ProcessingStatus.SUCCESS
        except Exception as e:
            event.error = str(e)
            event.status = ProcessingStatus.ERROR
        return event
        return event