from ctypes import ArgumentError
from musicfig import colors
from ..lego import DimensionsTagEvent
from ..nfc_tag import NFCTag, register_tag_type
from pubsub import pub

class PluginError(BaseException):
    pass

class BasePlugin:
    """
    Base class for implementing plugins

    The core use case of a plugin is to add functionality when one of various
    events occur, most commonly when a tag is added or removed from the Dimensions
    dimensions.

    The default functionality provided by this base plugin is:
    - Register an optional NFCTag classes so tags of that type can be created or acted
      upon. These will be concrete classes of type nfc_tag.NFCTag and should be defined
      in the custom plugin module. Defining this will filter the tag events which come
      in to only those pertaining to this type of NFCTag
    - Subscribe and respond to tag add and tag removed topics
    - Publish events for the following upon handling the add/remove topics:
      - add succeeded
      - add failed - this is accomplished by raising NFCTagOperationError in the handler
      - remove succeeded

    If one doesn't want to pair with an explicit tag (for example, looking to add some
    functionality which occurs for all tags, regardless of type), then initializing this
    with a None tag class will work. Further, one could register a tag but not respond
    to any events; this seems odd as nothing would happen when those tags are loaded,
    but one _could_ do it.
    """

    def __init__(self, tag_class):
        """
        Base initializer which must be overridden for proper functioning

        Positional arguments:
        tag_class -- a class object which extends NFCTag. Can be None if pairing
                     with a tag type is undesirable.
        """
        if tag_class is not None and not issubclass(tag_class, NFCTag):
            raise ArgumentError("`tag_class` must extend nfc_tag.NFCTag")
        self.tag_class = tag_class

    def init_app(self, app):
        """
        Flask-style initializer with the app context

        "Where do I put my member definitions?" You'll need to do anything which depends
        upon app context (for example, logging or config) in `init_app`.

        It's not recommended to override this method without calling `super().init_app(app)`

        Positional arguments:
        app -- a Flask application context object (or proxy)
        """
        self.app = app
        self.logger = app.logger
        self.register_event_listeners()
        self.register_tag_class()
    
    def _get_from_config_or_fail(self, config_key):
        """
        Helper function for getting a single key from the provided config

        Yes, we know that we could just let the caller access the key in config themselves
        and thus raise a KeyError, but this way we can do a more homogenous error which is
        easier to catch, plus we can do some help as to how to prevent future failure

        Positional arguments:
        config_key -- which key we're looking for
        """
        value = self.app.config.get(config_key)
        if value is None:
            raise PluginError("Must define %s in config" % config_key)
        return value
    
    def register_event_listeners(self):
        """
        Registers event listeners to connect with the rest of the app

        By default, we'll listen to all tag.added and tag.removed events', however if 
        listening to events is not your jam, feel free to override this method.
        """
        pub.subscribe(self.on_tag_added, "tag.added")
        pub.subscribe(self.on_tag_removed, "tag.removed")

    def register_tag_class(self):
        """
        Connects the NFCTag class to the NFCTagManager so Tags of this type can be
        built, added, and acted upon
        """
        if self.tag_class is not None:
            register_tag_type(self.tag_class)

    def on_tag_added(self, tag_event: DimensionsTagEvent, nfc_tag: NFCTag):
        """
        Handler for when tags get added.

        -- CAUTION --
        As with any Observer system, the event which is passed in here does not stop here; it
        will go to any listeners on this topic. Thus there are two _very important_ things to
        keep in mind.
        
        First, do not depend upon the event handlers being triggered in any particular
        order; for the purposes of your operation, this is the only event handler which exists.

        Second, do not modify the tag_event _in any way_; again, since you can't depend upon
        the order of operations, it is a mistake to try and manipulate future operations by
        changing the content of the event.

        Positional arguments:
        tag_event -- DimensionsTagEvent object contains information about the tag adding event
        nfc_tag -- NFCTag object representing the tag which was added
        """
        pass
    
    def on_tag_removed(self, tag_event: DimensionsTagEvent, nfc_tag: NFCTag):
        """
        Handler for when tags get removed.

        -- CAUTION --
        As with any Observer system, the event which is passed in here does not stop here; it
        will go to any listeners on this topic. Thus there are two _very important_ things to
        keep in mind.
        
        First, do not depend upon the event handlers being triggered in any particular
        order; for the purposes of your operation, this is the only event handler which exists.

        Second, do not modify the tag_event _in any way_; again, since you can't depend upon
        the order of operations, it is a mistake to try and manipulate future operations by
        changing the content of the event.

        Positional arguments:
        tag_event -- DimensionsTagEvent object contains information about the tag removal event
        nfc_tag -- NFCTag object representing the tag which was removed
        """
        pass

    def _get_success_pad_color(self):
        """ Returns the int tuple color (R, G, B) the pad should turn upon a tag add success """
        return colors.PURPLE

    def dispatch_add_error_event(self, tag_event: DimensionsTagEvent):
        """
        Publishes event in case of tag add handling failure

        Positional arguments:
        tag_event -- DimensionsTagEvent the event which triggered the failure 
        """
        pub.sendMessage("handler_response.add.error", tag_event=tag_event)
    
    def dispatch_add_success_event(self, tag_event: DimensionsTagEvent):
        """
        Publishes event in case of tag add handling success

        Positional arguments:
        tag_event -- DimensionsTagEvent the event which triggered the success
        """
        pub.sendMessage("handler_response.add.success", tag_event=tag_event, color=self._get_success_pad_color())
    
    def dispatch_remove_success_event(self, tag_event:DimensionsTagEvent):
        """
        Publishes event in case of tag remove handling failure

        Positional arguments:
        tag_event -- DimensionsTagEvent the event which triggered the failure 
        """
        pub.sendMessage("handler_response.remove.success", tag_event=tag_event)
    
    def dispatch_remove_error_event(self, tag_event:DimensionsTagEvent):
        """
        Publishes event in case of tag remove handling failure

        Positional arguments:
        tag_event -- DimensionsTagEvent the event which triggered the failure 
        """
        pub.sendMessage("handler_response.remove.error", tag_event=tag_event)