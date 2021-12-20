from .base import BasePlugin, PluginError

from ..lego import DimensionsTagEvent
from ..nfc_tag import NFCTag
from ..webhook import PostMixin


class WebhookTag(NFCTag, PostMixin):
    """
    NFCTag which represents a webhook


    Included in the core because webhooks are super common, so this can be a good starting point
    for anything which needs this functionality
    """
    required_attributes = ["added_url"]

    def _init_attributes(self):
        super()._init_attributes()
        self.added_url = self.attributes["added_url"]
        self.added_post_json = self.attributes.get("added_post_json")
        self.removed_url = self.attributes.get("removed_url")
        self.removed_post_json = self.attributes.get("removed.post_json")


class WebhookPlugin(BasePlugin, PostMixin):
    def __init__(self):
        super().__init__(WebhookTag)
    
    def on_tag_added(self, tag_event: DimensionsTagEvent, nfc_tag: NFCTag):
        super().on_tag_added(tag_event, nfc_tag)

        if not isinstance(nfc_tag, WebhookTag):
            return
        
        try:
            self.post_json(nfc_tag.added_url, nfc_tag.added_post_json)
        except Exception as e:
            self.logger.exception("failed calling added webhook")
            self.dispatch_add_error_event(tag_event)
            return
        
        self.dispatch_add_success_event(tag_event)

    
    def on_tag_removed(self, tag_event: DimensionsTagEvent, nfc_tag: NFCTag):
        super().on_tag_removed(tag_event, nfc_tag)

        if not isinstance(nfc_tag, WebhookTag):
            return

        if nfc_tag.removed_url is None:
            return
        
        try:
            self.post_json(nfc_tag.removed_url, nfc_tag.removed_post_json)
        except Exception as e:
            self.logger.exception("failed calling removed webhook")
            self.dispatch_remove_error_event(tag_event)
            return
        
        self.dispatch_remove_success_event(tag_event)

webhook_plugin = WebhookPlugin()