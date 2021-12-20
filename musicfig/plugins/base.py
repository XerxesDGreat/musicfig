from musicfig import colors
from ..lego import DimensionsTagEvent
from ..nfc_tag import NFCTag, register_tag_type
from pubsub import pub

class BasePlugin:
    def __init__(self, tag_class):
        self.tag_class = tag_class

    def init_app(self, app):
        self.logger = app.logger
        self.register_event_listeners()
        self.register_tag_class()
    
    def register_event_listeners(self):
        """
        Registers event listeners to connect with the rest of the app

        By default, we'll listen to all tag.added and tag.removed events
        """
        pub.subscribe(self.on_tag_added, "tag.added")
        pub.subscribe(self.on_tag_removed, "tag.removed")

    def register_tag_class(self):
        if self.tag_class is not None:
            register_tag_type(self.tag_class)

    def on_tag_added(self, tag_event: DimensionsTagEvent, nfc_tag: NFCTag):
        pass
    
    def on_tag_removed(self, tag_event: DimensionsTagEvent, nfc_tag: NFCTag):
        pass

    def _get_success_pad_color(self):
        return colors.PURPLE

    def dispatch_add_error_event(self, tag_event: DimensionsTagEvent):
        pub.sendMessage("handler_response.add.error", tag_event=tag_event)
    
    def dispatch_add_success_event(self, tag_event: DimensionsTagEvent):
        pub.sendMessage("handler_response.add.success", tag_event=tag_event, color=self._get_success_pad_color())
    
    def dispatch_remove_success_event(self, tag_event:DimensionsTagEvent):
        pub.sendMessage("handler_response.remove.success", tag_event=tag_event)