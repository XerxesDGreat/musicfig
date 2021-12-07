#!/usr/bin/env python

import os
import yaml
import logging

from musicfig import colors
from pathlib import Path

logger = logging.getLogger(__name__)

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
                self._tags = yaml.load(stream, Loader=yaml.FullLoader)
            self.last_updated = os.stat(self.tags_file).st_mtime
            self.tags = self._tags # temporary to keep the two similar

        return self._tags


    def get_tag_by_identifier(self, identifier):
        """
        Looks everywhere for a tag which is registered. Will return either
        old-style or new-style tags, depending on which store it comes from
        """
        tag = self.tags['identifier'].get(identifier)
        tag = self._tags['identifier'].get(identifier, tag)
        if tag is None:
            logger.info(self._tags)
            logger.info(self.tags)
            tag = UnknownTag(identifier)
        return tag


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
        # should _probably_ use a logger which is associated with the
        # app, but this is fine for now. Maybe
        logger.info('Discovered new tag: %s' % self.identifier)

    def get_pad_color(self):
        return colors.RED
