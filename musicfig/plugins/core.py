"""
The plugins contained herein are part of the core functionality
of the application. It will still work without them, but these
provide added creature comforts and are included separately.
"""

from .base import BasePlugin, PluginError
from .. import colors
from ..nfc_tag import UnknownTypeTag, UnregisteredTag, NFCTag
from ..lego import DimensionsTagEvent
from ..socketio import socketio


class UnregisteredTagPlugin(BasePlugin):
    """
    Plugin for handling events triggered by tags which aren't
    yet registered
    """

    def __init__(self):
        super().__init__(UnregisteredTag)
    
    def on_tag_added(self, tag_event: DimensionsTagEvent, nfc_tag: NFCTag):
        super().on_tag_added(tag_event, nfc_tag)

        # should _probably_ use a logger which is associated with the
        # app, but this is fine for now. Maybe
        self.logger.info('Discovered new tag: %s' % tag_event.identifier)
        socketio.emit("new_tag", {"tag_id": tag_event.identifier})

    def _get_success_pad_color(self):
        return colors.YELLOW

unregistered_tag_plugin = UnregisteredTagPlugin()