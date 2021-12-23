import json

from .core import BasePlugin
from ..lego import DimensionsTagEvent
from ..nfc_tag import NFCTag, NFCTagOperationError
from ..webhook import PostMixin


class WebhookTag(NFCTag, PostMixin):
    """
    NFCTag which represents a webhook


    Included in the core because webhooks are super common, so this can be a good starting point
    for anything which needs this functionality
    """
    required_attributes = ["added_url"]

    @classmethod
    def get_attributes_description(cls):
        return json.dumps({
            "added_url": "[Required] The url to call when the tag is added",
            "added_post_json": "[Optional] JSON payload to send to the added url call. Default is empty string",
            "removed_url": "[Optional] The url to call when the tag is removed",
            "removed_post_json": "[Optional] JSON payload to send with the removed url call. Only used when there is a removed_url defined. Default is empty string"
        }, indent=4)

    def _init_attributes(self):
        super()._init_attributes()
        self.added_url = self.attributes["added_url"]
        self.added_post_json = self.attributes.get("added_post_json")
        self.removed_url = self.attributes.get("removed_url")
        self.removed_post_json = self.attributes.get("removed.post_json")


class WebhookPlugin(BasePlugin, PostMixin):

    TAG_CLASS = WebhookTag
    
    def _on_tag_added(self, tag_event: DimensionsTagEvent, nfc_tag: NFCTag):
        try:
            self.post_json(nfc_tag.added_url, nfc_tag.added_post_json)
        except Exception as e:
            raise NFCTagOperationError("Got exception (%s) calling add post hook: %s", e.__name__, str(e))

    
    def _on_tag_removed(self, tag_event: DimensionsTagEvent, nfc_tag: NFCTag):
        if nfc_tag.removed_url is None:
            return
        
        try:
            self.post_json(nfc_tag.removed_url, nfc_tag.removed_post_json)
        except Exception as e:
            raise NFCTagOperationError("Got exception (%s) calling remove post hook: %s", e.__name__, str(e))

webhook_plugin = WebhookPlugin()