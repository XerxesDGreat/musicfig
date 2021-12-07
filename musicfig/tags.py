#!/usr/bin/env python

import os
import yaml
import logging

from musicfig import colors
from musicfig import webhook
from pathlib import Path

logger = logging.getLogger(__name__)


class NFCTag():
    def __init__(self, identifier):
        self.identifier = identifier
    

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


class WebhookTag(NFCTag):
    def __init__(self, identifier, **kwargs):
        if 'webhook' not in kwargs:
            raise KeyError("missing required key 'webhook'")
        super().__init__(identifier)
        self.webhook_url = kwargs["webhook"]
        
    def on_add(self):
        super().on_add()
        self._post_to_url(self.webhook_url)

    def _post_to_url(self, url, request_body={}):
        try:
            return webhook.Requests.post(url, request_body)
        except BaseException as e:
            logger.exception("Failed to execute webhook")


class Tags():

    def __init__(self, should_load_tags=True):
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
                self.tags = yaml.load(stream, Loader=yaml.FullLoader)['identifier']
            self._tags = {k: Tags.tag_factory(k, v) for (k,v) in self.tags.items()}
            self._tags = {k: v for (k, v) in self._tags.items() if v is not None}
            self.last_updated = os.stat(self.tags_file).st_mtime
            logger.info("loaded %s into _tags, %s into tags", len(self._tags), len(self.tags))

        return self._tags
    

    tag_registry_map = {
        "webhook": WebhookTag
    }
    def tag_factory(identifier, tag_definition):
        # TODO build a composite tag in case we want to do e.g. spotify + webhook
        tag = None
        for k, v in tag_definition.items():
            if k in Tags.tag_registry_map:
                tag = Tags.tag_registry_map[k](identifier, **tag_definition)
                break
        return tag


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