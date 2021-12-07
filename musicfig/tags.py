#!/usr/bin/env python

import os
import yaml
import logging

from musicfig import colors
from musicfig import webhook
from pathlib import Path

logger = logging.getLogger(__name__)


class NFCTag():
    def __init__(self, identifier, required_kwargs=[], app_context=None, **kwargs):
        self.identifier = identifier
        self.app_context = app_context
        self._verify_kwargs(required_kwargs, **kwargs)
    
    def _verify_kwargs(self, required_kwargs, **kwargs):
        for required_kwarg in required_kwargs:
            if required_kwarg not in kwargs:
                raise KeyError("missing required key '%s'" % required_kwarg)

    def on_add(self):
        pass

    def on_remove(self):
        pass
    
    def get_pad_color(self):
        return colors.OFF

    def should_do_light_show(self):
        return True


class UnknownTag(NFCTag):
    def on_add(self):
        super().on_add()
        # should _probably_ use a logger which is associated with the
        # app, but this is fine for now. Maybe
        logger.info('Discovered new tag: %s' % self.identifier)

    def get_pad_color(self):
        return colors.RED


class WebhookMixin():
    def _post_to_url(self, url, request_body={}):
        try:
            return webhook.Requests.post(url, request_body)
        except BaseException as e:
            logger.exception("Failed to execute webhook")


class WebhookTag(NFCTag, WebhookMixin):
    required_kwargs = ["url"]

    def __init__(self, identifier, app_context=None, **kwargs):
        super().__init__(identifier,
            required_kwargs=WebhookTag.required_kwargs,
            app_context=app_context,
            **kwargs)
        self.webhook_url = kwargs["url"]
        
    def on_add(self):
        super().on_add()
        self._post_to_url(self.webhook_url)


class SlackTag(NFCTag, WebhookMixin):
    required_kwargs = ["text"]

    def __init__(self, identifier, app_context=None, **kwargs):
        super().__init__(
            identifier,
            required_kwargs=SlackTag.required_kwargs,
            app_context=app_context,
            **kwargs
        )
        self.webhook_url = app_context.config.get("SLACK_WEBHOOK_URL")
        self.text = kwargs["text"]
    
    def on_add(self):
        super().on_add()
        self._post_to_url(self.webhook_url, {"text": self.text})






class Tags():

    def __init__(self, app_context=None, should_load_tags=True):
        self.app_context = app_context
        current_dir = os.path.dirname(os.path.abspath(__file__))
        if Path(current_dir + '/../tags.yml').is_file():
            self.tags_file = current_dir + '/../tags.yml'
        if Path('/config/tags.yml').is_file():
            self.tags_file = '/config/tags.yml'
            
        self.last_updated = -1
        self.tags = {}
        self._tags = {}

        if should_load_tags:
            self.load_tags()


    def load_tags(self):
        """Load the NFC tag config file if it has changed.
        """
        if (self.last_updated != os.stat(self.tags_file).st_mtime):
            with open(self.tags_file, 'r') as stream:
                self.tags = yaml.load(stream, Loader=yaml.FullLoader)
            self._tags = {k: self.tag_factory(k, v) for (k,v) in self.tags.items()}
            self._tags = {k: v for (k, v) in self._tags.items() if v is not None}
            self.last_updated = os.stat(self.tags_file).st_mtime
            logger.info("loaded %s into new form of tags, %s into old form of", len(self._tags), len(self.tags))

        return self._tags
    

    tag_registry_map = {
        "webhook": WebhookTag,

    }
    def tag_factory(self, identifier, tag_definition):
        # TODO build a composite tag in case we want to do e.g. spotify + webhook;
        # perhaps do a list of types or something?
        tag = None
        tag_type = tag_definition.get("type")
        if tag_type is None:
            return tag
        
        tag_class = Tags.tag_registry_map.get(tag_type)
        if tag_class is None:
            return tag

        return tag_class(identifier, app_context=self.app_context, **tag_definition)


    def get_tag_by_identifier(self, identifier):
        """
        Looks everywhere for a tag which is registered. Will return either
        old-style or new-style tags, depending on which store it comes from.
        New style will override old style
        """
        tag = self._tags.get(identifier)
        if tag is None:
            tag = self.tags.get(identifier)
        if tag is None:
            logger.info(self._tags)
            logger.info(self.tags)
            tag = UnknownTag(identifier)
        return tag