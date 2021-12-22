import random
import threading
import time


from . import colors
from .lego import Dimensions, FakeDimensions, DimensionsTagEvent
from .nfc_tag import NFCTagManager, NFCTag, NFCTagOperationError
from pubsub import pub
from usb.core import USBError

class MainLoop(threading.Thread):
    """
    Manages the application loop for working with the Dimensions base

    The main set of tasks contained within is to poll for dimensions
    tag events, map them to database records, and dispatch events to the 
    event dispatcher for later handling.
    """

    USB_ERROR_THRESHOLD = 5

    def __init__(self, group=None, target=None, name=None, args=(), kwargs=None, *, daemon=None):
        super().__init__(group=group, target=target, name=name, args=args, kwargs=kwargs, daemon=daemon)
        self.current_active_tags = set() # this may be better in the Dimensions
        self.do_loop = True
        self.error_count = 0

    def init_app(self, app):
        """
        Flask-stype initializer for stuff which relies on app context.

        Gets the Dimension threaded loop ready to run within an application context.

        Positional arguments:
        app -- an instance of the Flask app, or at least its proxy
        """
        self.app = app
        self.logger = app.logger
        self.dimensions = FakeDimensions(app) if app.config.get("USE_MOCK_PAD") else Dimensions(app)
        with app.app_context():
            # @todo make this configurable somehow
            self.nfc_tag_manager = NFCTagManager.get_instance() # maybe turn this into an init_app() as well

        self.logger.info("in init id: %s", id(self.dimensions))
        self._init_event_handlers()
    
    def _init_event_handlers(self):
        """ Sets up the event handlers """
        pub.subscribe(self.on_tag_added_error, "handler_response.add.error")
        pub.subscribe(self.on_tag_added_success, "handler_response.add.success")
        pub.subscribe(self.on_tag_removed_success, "handler_response.remove.success")
        pub.subscribe(self.on_tag_removed_error, "handler_response.remove.error")
        pub.subscribe(self.on_tag_being_processed, "handler_response.processing_started")
        pub.subscribe(self.on_tag_created, "tag_created")
    
    def stop_loop(self):
        """ Sets a flag to stop the loop. Note that the loop will stop after the current iteration"""
        self.do_loop = False

    def run(self):
        """
        Main loop of the program

        Responsible for fetching events from the pad and handling them accordingly
        """
        self.dimensions.change_pad_color(Dimensions.ALL_PAD, self.get_idle_color())
        with self.app.app_context():
            while self.do_loop:
                if random.randint(1, 10000) == 0:
                    self.logger.info("loop")
                
                try:
                    tag_event = self.dimensions.get_tag_event()
                except USBError as e:
                    # This most likely means the pad has been disconnected. Either way,
                    # we'll give it a chance to correct itself, but kill the process
                    # if the error doesn't seem to resolve
                    self.error_count = self.error_count + 1
                    if self.error_count < self.USB_ERROR_THRESHOLD:
                        self.logger.error("Perhaps disconnected; trying again after a bit...")
                        time.sleep(1)
                    else:
                        self.logger.error("Likely unrecoverable, assuming dead; stopping the loop")
                        # well, we tried a few times, kill the loop
                        self.stop_loop()

                if tag_event is None:
                    continue

                try:
                    nfc_tag = self.nfc_tag_manager.get_nfc_tag_by_id(tag_event.identifier)
                    self.update_active_tags(tag_event, nfc_tag)
                    self.publish_tag_event(tag_event, nfc_tag)
                except Exception as e:
                    self.logger.exception("encountered exception trying to do tag stuff")
                    self.error_flash(tag_event.pad_num)
    
    def publish_tag_event(self, tag_event: DimensionsTagEvent, nfc_tag: NFCTag):
        """
        Sends a tag added/removed event to be handled by the appropriate listener (if any)

        Add event listeners using plugins in the plugin module
        
        Positional arguments:
        tag_event -- DimensionsTagEvent containing details about the event
        nfc_tag -- the tag which triggered the event
        """
        topic = "tag.removed" if tag_event.was_removed else "tag.added"
        pub.sendMessage(topic, tag_event=tag_event, nfc_tag=nfc_tag)

    def update_active_tags(self, tag_event: DimensionsTagEvent, nfc_tag: NFCTag):
        """
        Updates the tag which is currently active

        Positional arguments:
        tag_event -- DimensionsTagEvent containing details about the event
        nfc_tag -- the tag which triggered the event
        """
        if tag_event.was_removed:
            self.current_active_tags.discard(nfc_tag) # discard doesn't raise an error if the item isn't in the set
        else:
            self.current_active_tags.add(nfc_tag)

    def error_flash(self, pad_num):
        """
        Flashes the indicated pad with the error color

        Positional arguments:
        pad_num -- index of the pad to flash
        """
        self.dimensions.flash_pad_color(pad=pad_num, on_length=8, off_length=8, pulse_count=4, colour=self.get_error_color())

    ###############################
    # Event handlers
    ###############################
    def on_tag_added_error(self, tag_event: DimensionsTagEvent):
        """
        Handler for when processing a tag addition emits an error event

        Positional arguments:
        tag_event -- DimensionsTagEvent containing details about the event
        """
        self.logger.debug("tag response event handled: %s", tag_event)
        self.error_flash(tag_event.pad_num)
    
    def on_tag_added_success(self, tag_event: DimensionsTagEvent, color=None):
        """
        Handler for when processing a tag addition emits a success event

        Positional arguments:
        tag_event -- DimensionsTagEvent containing details about the event
        color -- optional int tuple representing which color the pad should become (R, G, B)
                 If color is None, will not attempt to change the color
        """
        if color is not None:
            self.dimensions.fade_pad_color(pad=tag_event.pad_num, pulse_time=10,
                                           pulse_count=1, colour=color)
        self.logger.debug("tag response event handled: %s, color: %s", tag_event, color)
    
    def on_tag_removed_success(self, tag_event: DimensionsTagEvent):
        """
        Handler for when processing a tag removal emits a success event

        Positional arguments:
        tag_event -- DimensionsTagEvent containing details about the event
        """
        self.dimensions.fade_pad_color(pad=tag_event.pad_num, pulse_time=10,
                                       pulse_count=1, colour=self.get_idle_color())
        self.logger.debug("tag response event handled: %s", tag_event)

    def on_tag_removed_error(self, tag_event: DimensionsTagEvent):
        """
        Handler for when processing a tag removal emits an error event

        Positional arguments:
        tag_event -- DimensionsTagEvent containing details about the event
        """
        self.logger.debug("tag response event handled: %s", tag_event)
        self.error_flash(tag_event.pad_num)
    
    def on_tag_being_processed(self, tag_event: DimensionsTagEvent, color=None):
        """
        Handler for when a tag has begun to be processed

        Positional arguments:
        tag_event -- DimensionsTagEvent containing details about the event
        color -- optional int tuple representing which color the pad should pulse (R, G, B)
                 If color is None, will not attempt to change the color
        """
        if color is not None:
            self.dimensions.fade_pad_color(pad=tag_event.pad_num, pulse_time=8, pulse_count=100, colour=color)
        self.logger.debug("tag is currently being processed: %s, color: %s", tag_event, color)
    
    def on_tag_created(self):
        """ Handler for when a new tag has been created """
        self.dimensions.flash_pad_color(pad=Dimensions.ALL_PAD, on_length=8, off_length=8, pulse_count=4, colour=colors.GREEN)

    ###############################
    # Color handling
    ###############################
    def get_idle_color(self):
        return self.app.config.get("DEFAULT_IDLE_COLOR", colors.DIM)
    
    def get_error_color(self):
        return self.app.config.get("DEFAULT_ERROR_COLOR", colors.RED)
    
    def get_default_active_color(self):
        return self.app.config.get("DEFAULT_ACTIVE_COLOR", colors.BLUE)
    
    def get_thinking_color(self):
        return self.app.config.get("DEFAULT_THINKING_COLOR", colors.PURPLE)