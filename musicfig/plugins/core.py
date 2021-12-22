"""
The plugins contained herein are part of the core functionality
of the application. It will still work without them, but these
provide added creature comforts and are included separately.
"""
from .. import colors
from ..nfc_tag import UnregisteredTag, NFCTag, NFCTagOperationError, NFCTagManager
from ..lego import DimensionsTagEvent
from ..socketio import socketio
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

    def __init__(self):
        """
        Base initializer which must be overridden for proper functioning
        """
        tag_class = getattr(self, "TAG_CLASS") if hasattr(self, "TAG_CLASS") else None
        if tag_class is not None and not issubclass(tag_class, NFCTag):
            raise ValueError("if defined, `tag_class` must extend nfc_tag.NFCTag")
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
            NFCTagManager.register_tag_type(self.tag_class)

    def _get_success_pad_color(self):
        """ Returns the int tuple color (R, G, B) the pad should turn upon a tag add success """
        return colors.PURPLE

    ############################
    # Event Handlers - Do not override
    ############################
    def on_tag_added(self, tag_event: DimensionsTagEvent, nfc_tag: NFCTag) -> None:
        """
        Handler for when tags get added.

        This method is the core logistical functionality of this event handler; thus it should
        not be overridden. To customize what happens when a tag event comes in, customize
        `_on_tag_added` instead.

        If a tag type is registered, this method will filter out any events without that tag
        type before passing it into the logic handler.

        If the logic handler raises an NFCTagOperationError, it will be caught and dispatch
        an error event; otherwise it will dispatch a success event.

        Positional arguments:
        tag_event -- DimensionsTagEvent object contains information about the tag adding event
        nfc_tag -- NFCTag object representing the tag which was added
        """
        self._on_tag_event(tag_event=tag_event, nfc_tag=nfc_tag, work_operation=self._on_tag_added,
                           success_event_dispatcher=self.dispatch_add_success_event,
                           error_event_dispatcher=self.dispatch_add_error_event)
    
    def on_tag_removed(self, tag_event: DimensionsTagEvent, nfc_tag: NFCTag) -> None:
        """
        Handler for when tags get removed.
        
        This method is the core logistical functionality of this event handler; thus it should
        not be overridden. To customize what happens when a tag event comes in, customize
        `_on_tag_removed` instead.

        If a tag type is registered, this method will filter out any events without that tag
        type before passing it into the logic handler.

        If the logic handler raises an NFCTagOperationError, it will be caught and dispatch
        an error event; otherwise it will dispatch a success event.

        Positional arguments:
        tag_event -- DimensionsTagEvent object contains information about the tag adding event
        nfc_tag -- NFCTag object representing the tag which was added
        """
        self._on_tag_event(tag_event=tag_event, nfc_tag=nfc_tag, work_operation=self._on_tag_removed,
                           success_event_dispatcher=self.dispatch_remove_success_event,
                           error_event_dispatcher=self.dispatch_remove_error_event)
    
    def _on_tag_event(self,
                     tag_event: DimensionsTagEvent,
                     nfc_tag: NFCTag,
                     work_operation,
                     success_event_dispatcher, 
                     error_event_dispatcher):
        """
        Generic event handling operations; exists because DRY.

        For details about what it does, read on_tag_added or on_tag_removed
        
        Positional arguments:
        tag_event -- DimensionsTagEvent object contains information about the tag adding event
        nfc_tag -- NFCTag object representing the tag which was added
        work_operation -- callable for the event handling to be done
        success_event_dispatcher -- callable for dispatching a success event
        error_event_dispatcher -- callable for dispatching an error event
        """
        if not isinstance(nfc_tag, self.tag_class):
            return
        
        try:
            work_operation(tag_event, nfc_tag)
        except NFCTagOperationError as e:
            self.logger.exception("%s failed; tag_event: %s, nfc_tag: %s", work_operation.__name__, tag_event, nfc_tag)
            error_event_dispatcher(tag_event)
        else:
            success_event_dispatcher(tag_event)


    ############################
    # Customizable Event Handlers
    ############################
    def _on_tag_added(self, tag_event: DimensionsTagEvent, nfc_tag: NFCTag) -> None:
        """
        Customizable handler for when tags get added

        This method should include the business logic of what happens when a tag is added.

        If a tag type is registered for this plugin, only events with that tag type will
        get into this method. 

        If this method raises an NFCTagOperationError, an error event will be dispatched; else
        a success event will be dispatched

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

    def _on_tag_removed(self, tag_event: DimensionsTagEvent, nfc_tag: NFCTag) -> None:
        """
        Customizable handler for when tags get added

        This method should include the business logic of what happens when a tag is added.

        If a tag type is registered for this plugin, only events with that tag type will
        get into this method. 

        If this method raises an NFCTagOperationError, an error event will be dispatched; else
        a success event will be dispatched

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


    ############################
    # Event Dispatchers
    ############################
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


class UnregisteredTagPlugin(BasePlugin):
    """
    Plugin for handling events triggered by tags which aren't
    yet registered
    """

    TAG_CLASS = UnregisteredTag
    
    def _on_tag_added(self, tag_event: DimensionsTagEvent, nfc_tag: NFCTag):

        # should _probably_ use a logger which is associated with the
        # app, but this is fine for now. Maybe
        self.logger.info('Discovered new tag: %s' % tag_event.identifier)
        socketio.emit("new_tag", {"tag_id": tag_event.identifier})

    def _get_success_pad_color(self):
        return colors.YELLOW

unregistered_tag_plugin = UnregisteredTagPlugin()