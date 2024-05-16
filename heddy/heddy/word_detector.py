import os
from pocketsphinx import LiveSpeech, get_model_path
from heddy.application_event import ApplicationEvent, ProcessingStatus
from heddy.resources import get_resource_dir
from queue import Queue
from threading import Thread


class WordDetector:
    def __init__(self, kws_path=None, model_path=None,) -> None:
        self.kws_path = kws_path or os.path.join(get_resource_dir(), "keywords.kws")
        self.model_path = model_path or get_model_path()
        self.queue = Queue()
        self.thread = None
        self.suspended = False
    
    def run(self,):
        print(f"Model Path: {self.model_path}")
        print(f"Keywords File Path: {self.kws_path}")

        speech = LiveSpeech(
            verbose=False,  # Set to True for detailed logs from PocketSphinx
            sampling_rate=16000,
            buffer_size=256,
            no_search=False,
            full_utt=False,
            hmm=os.path.join(self.model_path, 'en-us/en-us'),
            lm=None,
            kws=self.kws_path
        )
        print("PocketSphinx initialized successfully.")
        print("Listening for keywords...")

        for phrase in speech:
            detected_words = [seg[0].lower().strip() for seg in phrase.segments(detailed=True)]  # Extract words
            print(f"Detected words: {detected_words}")  # Log for debugging
            for word in detected_words:
                if self.suspended:
                    continue
                self.queue.put(word)
            
        
    def run_thread(self,):
        self.thread = Thread(target=self.run)
        self.thread.start()
        
    def listen(self, event: ApplicationEvent):
        if self.thread is None:
            self.run_thread()
        self.suspended = False
        detected_words = self.queue.get()
        event.result = detected_words
        event.status = ProcessingStatus.SUCCESS
        return event
    
    def clear(self,):
        # HACK: this is hacky but should work
        self.queue = Queue()
        self.suspended = True
        
        

if __name__ == "__main__":
    WordDetector().run()