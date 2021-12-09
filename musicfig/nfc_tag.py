#!/usr/bin/env python

import json
import logging
import os
import sqlite3
import time
import xled
import yaml

from flask_sqlalchemy import SQLAlchemy
from musicfig import colors, webhook
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


class TwinklyTag(NFCTag):
    control_interface = None
    required_kwargs = ["pattern"]

    def __init__(self, identifier, app_context=None, **kwargs):
        super().__init__(
            identifier,
            required_kwargs=TwinklyTag.required_kwargs,
            app_context=app_context,
            **kwargs
        )
        self.pattern_dir = app_context.config.get("TWINKLY_PATTERN_DIR",
            os.path.join("..", "assets", "twinkly_patterns"))
        self.pattern = kwargs["pattern"]

    def _get_control_interface(self):
        if TwinklyTag.control_interface is not None:
            return TwinklyTag.control_interface
        
        ip_address = self.app_context.config.get("TWINKLY_IP_ADDRESS")
        mac_address = self.app_context.config.get("TWINKLY_MAC_ADDRESS")
        if ip_address and mac_address:
            TwinklyTag.control_interface = xled.ControlInterface(ip_address, mac_address)
        else:
            logger.warning("Need config values to initialize Twinkly")

        return TwinklyTag.control_interface
    
    def on_add(self):
        """
        pattern is set tree mode to off, send movie, update effects settings, and set tree mode to on
        """
        logger.info("Twinkly - requested pattern %s", self.pattern)
        pattern_file = os.path.join(self.pattern_dir, self.pattern)
        if not os.path.isfile(pattern_file):
            logger.warning("Requested pattern %s does not exist at %s", self.pattern, pattern_file)
            return

        ctrl = self._get_control_interface()

        # we'll need these for calculations
        num_leds = ctrl.get_device_info()['number_of_led']
        bytes_per_frame = num_leds * 3

        # do the tree
        r = ctrl.set_mode("off")
        logger.info("Twinkly - %s", r.data)
        with open(pattern_file, 'rb') as f:
            r = ctrl.set_led_movie_full(f)
            logger.info("Twinkly - %s", r.data)
            
            # also need the size of the file
            num_frames = r.data.get("frames_number")
        
        # calc num frames
        if num_frames is None:
            file_size = os.path.getsize(pattern_file)
            num_frames = int(file_size / bytes_per_frame)

        logger.info("Twinkly - movie config - num_leds: %s, bytes per frame: %s, num_frames: %s", num_leds, bytes_per_frame, num_frames)
        r = ctrl.set_led_movie_config(40, num_frames, num_leds)
        logger.info("Twinkly - %s", r.data)
        r = ctrl.set_mode("movie")
        logger.info("Twinkly - %s", r.data)


class NFCTagStore():


    def __init__(self, app_context):
        self.db_uri = app_context.config.get('SQLITE_URI')
        self.db_conn = sqlite3.connect(self.db_uri, check_same_thread=False)
        self.cursor = self.db_conn.cursor()
        self.create_table()


    def create_table(self):
        query = "CREATE TABLE IF NOT EXISTS nfc_tags (\
                id text UNIQUE, \
                name text, \
                description text, \
                type text, \
                attr text, \
                last_updated integer \
            )"
        self.cursor.execute(query)
        self.db_conn.commit()
    

    def get_last_updated_time(self):
        query = "SELECT last_updated\
                    FROM nfc_tags\
                    ORDER BY last_updated DESC\
                    LIMIT 1"
        last_updated_db = self.cursor.execute(query).fetchone()
        if last_updated_db is None:
            last_updated_db = 0
        return last_updated_db
    

    def populate_from_dict(self, nfc_tag_dict):
        """
        Expects nfc tag dict with the keys as unique identifiers and the
        values as the configuration information. This will be parsed and
        certain keywords will be pulled into explicit fields and removed
        from the config:
        - name or _name (the former overrules) -> `name`
        - desc or description (the latter overrules) -> `description`
        - type -> `type`
        Everything that is remaining will be encoded as json and stored in 
        the `attr` field
        """
        before = self.cursor.execute("SELECT COUNT(*) FROM nfc_tags").fetchone()
        def convert_one(k, v, curtime):
            id = k
            # these double-pops actually pull both of the keys from the dictionary;
            # this is intentional as we don't want them to stick around afterward
            name = v.pop("name", v.pop("_name", None))
            desc = v.pop("description", v.pop("desc", None))
            nfc_tag_type = v.get("type", None)
            attr = json.dumps(v)
            return (id, name, desc, nfc_tag_type, attr, curtime)

        cur_time = NFCTagStore.get_current_timestamp()
        replacement_list = [convert_one(k, v, cur_time) for (k, v) in nfc_tag_dict.items()]
        
        query = "INSERT OR REPLACE INTO nfc_tags VALUES (?, ?, ?, ?, ?, ?)"
        self.cursor.executemany(query, replacement_list)
        after = self.cursor.execute("SELECT COUNT(*) FROM nfc_tags").fetchone()
        logger.info("added %s tags; before: %s, after: %s", len(nfc_tag_dict.items()), before, after)
        self.conn.commit()
        


    def get_current_timestamp():
        return int(time.time())


TAG_REGISTRY_MAP = {
    "webhook": WebhookTag,
    "slack": SlackTag,
    "twinkly": TwinklyTag,
}

class TagManager():


    def __init__(self, app_context=None, should_load_tags=True):
        self.app_context = app_context
        self.nfc_tags_file = app_context.config.get("NFC_TAG_FILE")
        self.last_updated = -1
        self.tags = {}
        self._tags = {}
        self.nfc_tag_store = NFCTagStore(app_context)

        if self.should_import_file():
            self.import_file()

        if should_load_tags:
            self.load_tags()

    def should_import_file(self):
        """
        This is not a super smart way of doing things, but it should work. tl;dr,
        if the modified time of the yaml file is more recent than the most recent
        modified time of any nfc_tag in the db, then we should update.

        *** note, this is destructive in nature; yaml will completely overwrite
        the database ***
        """
        last_db_update = self.nfc_tag_store.get_last_updated_time()
        last_file_update = int(os.stat(self.nfc_tags_file).st_mtime)
        logger.info("last db updated: %s, last file updated: %s", last_db_update, last_file_update)
        return last_file_update > last_db_update
    

    def import_file(self):
        with open(self.nfc_tags_file, 'r') as f:
            nfc_tag_defs = yaml.load(f, Loader=yaml.FullLoader)
        self.nfc_tag_store.populate_from_dict(nfc_tag_defs)

    def load_tags(self):
        """
        Load the NFC tag config file if it has changed.
        """
        if (self.last_updated != os.stat(self.nfc_tags_file).st_mtime):
            with open(self.nfc_tags_file, 'r') as stream:
                self.tags = yaml.load(stream, Loader=yaml.FullLoader)
            self._tags = {k: self.tag_factory(k, v) for (k,v) in self.tags.items()}
            self._tags = {k: v for (k, v) in self._tags.items() if v is not None}
            self.last_updated = os.stat(self.nfc_tags_file).st_mtime
            logger.info("loaded %s into new form of tags, %s into old form of", len(self._tags), len(self.tags))

        return self._tags


    def tag_factory(self, identifier, tag_definition):
        # TODO build a composite tag in case we want to do e.g. spotify + webhook;
        # perhaps do a list of types or something?
        tag = None
        tag_type = tag_definition.get("type")
        if tag_type is None:
            return tag
        
        tag_class = TAG_REGISTRY_MAP.get(tag_type)
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