from heddy.assistant.conversation import Conversation


class FakeTimer:
    def __init__(self, interval, function):
        self.interval = interval
        self.function = function
        self.started = False
        self.cancelled = False
        self.daemon = False

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def fire(self):
        self.function()


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make(timeout=90.0, on_reset=None):
    clock = Clock()
    timers = []

    def factory(interval, function):
        timer = FakeTimer(interval, function)
        timers.append(timer)
        return timer

    conversation = Conversation(timeout, on_reset=on_reset, clock=clock, timer_factory=factory)
    return conversation, clock, timers


def test_starts_without_context():
    conversation, _, _ = make()
    assert conversation.previous_response_id is None
    assert not conversation.is_active


def test_touch_remembers_the_response_and_arms_a_daemon_timer():
    conversation, _, timers = make(timeout=30)
    conversation.touch("resp_1")
    assert conversation.previous_response_id == "resp_1"
    assert conversation.is_active
    assert len(timers) == 1 and timers[0].started and timers[0].daemon
    assert timers[0].interval == 30


def test_context_expires_by_clock_even_if_the_timer_never_fires():
    conversation, clock, _ = make(timeout=90)
    conversation.touch("resp_1")
    clock.now += 89
    assert conversation.previous_response_id == "resp_1"
    clock.now += 1
    assert conversation.previous_response_id is None


def test_timer_expiry_drops_context_and_notifies_once():
    resets = []
    conversation, _, timers = make(on_reset=lambda: resets.append(True))
    conversation.touch("resp_1")
    timers[0].fire()
    assert conversation.previous_response_id is None
    assert resets == [True]
    timers[0].fire()  # a stale timer firing again is harmless
    assert resets == [True]


def test_retouching_cancels_the_previous_timer():
    conversation, _, timers = make()
    conversation.touch("resp_1")
    conversation.touch("resp_2")
    assert timers[0].cancelled and not timers[1].cancelled
    assert conversation.previous_response_id == "resp_2"


def test_manual_reset_is_silent():
    resets = []
    conversation, _, timers = make(on_reset=lambda: resets.append(True))
    conversation.touch("resp_1")
    conversation.reset()
    assert conversation.previous_response_id is None
    assert timers[0].cancelled
    assert resets == []
