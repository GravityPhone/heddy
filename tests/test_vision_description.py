from heddy import main_controller
from heddy.application_event import ApplicationEvent, ApplicationEventType

args = main_controller.parse_cli_args()
controller = main_controller.initialize(args)
controller.run(
    ApplicationEvent(type=ApplicationEventType.GET_SNAPSHOT,
    request = "Describe the image."
    )
)