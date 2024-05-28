from heddy.application_event import ApplicationEvent, ProcessingStatus, ApplicationEventType
import json
import requests

def send_text_message(arguments):
    webhook_url = "https://hooks.zapier.com/hooks/catch/82343/19816978ac224264aa3eec6c8c911e10/"
    
    # Parse the arguments as JSON if it's a string
    if isinstance(arguments, str):
        arguments = json.loads(arguments)
    
    # Access the 'message' key instead of 'text'
    text_to_send = arguments.get('message', '')  # Default to empty string if 'message' not found
    
    payload = {"text": text_to_send}
    print(f"Sending text message via Zapier with arguments: {arguments}")
    response = requests.post(webhook_url, json=payload)
    print(f"Response from Zapier: {response.status_code}, {response.text}")
    if response.status_code == 200:
        return "Success!"
    else:
        raise RuntimeError(f"Failed with {response.status_code=}")
    
class ZapierManager:
    def handle_message(self, event: ApplicationEvent):
        try:
            tool_calls = event.data.required_action.submit_tool_outputs.tool_calls
            results = []
            for call in tool_calls:
                if call.function.name == "send_text_message":
                    print(f"Calling send_text_message with arguments: {call.function.arguments}")
                    result = send_text_message(call.function.arguments)
                    print(f"Result from send_text_message: {result}")
                    results.append({"tool_call_id": call.id, "output": result})
            event.result = results
            event.status = ProcessingStatus.SUCCESS
        except Exception as e:
            event.error = str(e)
            event.status = ProcessingStatus.ERROR
        return event
