#!/usr/bin/env python

import json
import logging
import os
import time
import xled
import yaml

from . import socketio
from .models import db, NFCTagModel
from flask import Blueprint, request, render_template, \
                  flash, g, session, redirect, url_for, \
                  current_app
from musicfig import colors, webhook
from pathlib import Path
from sqlalchemy import func

logger = logging.getLogger(__name__)

# all uses of current_app or app_context in here are for config; try just passing those
# config values, mayhap?

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
        socketio.emit('new_tag', {"id": self.identifier})

    def get_pad_color(self):
        return colors.RED


class LegacyTag(NFCTag):
    def __init__(self, identifier, app_context=None, **kwargs):
        super().__init__(identifier, app_context=app_context)
        self.definition = kwargs


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

    def _get_pattern_file(self):
        pattern_file = os.path.join(self.pattern_dir, self.pattern)
        if not os.path.isfile(pattern_file):
            logger.warning("Requested pattern %s does not exist at %s", self.pattern, pattern_file)
            return None
        return pattern_file
    
    def on_add(self):
        """
        pattern is set tree mode to off, send movie, update effects settings, and set tree mode to on
        """
        logger.debug("Twinkly - requested pattern %s", self.pattern)
        pattern_file = self._get_pattern_file()
        if pattern_file is None:
            return

        ctrl = self._get_control_interface()

        # we'll need these for calculations
        num_leds = ctrl.get_device_info()['number_of_led']
        bytes_per_frame = num_leds * 3

        # do the tree
        r = ctrl.set_mode("off")
        with open(pattern_file, 'rb') as f:
            r = ctrl.set_led_movie_full(f)
            
            # also need the size of the file
            num_frames = r.data.get("frames_number")
        
        # calc num frames
        if num_frames is None:
            file_size = os.path.getsize(pattern_file)
            num_frames = int(file_size / bytes_per_frame)

        r = ctrl.set_led_movie_config(40, num_frames, num_leds)
        r = ctrl.set_mode("movie")


class NFCTagStore():
    @staticmethod
    def get_last_updated_time():
        latest_nfc_tag = NFCTagModel.query.order_by(NFCTagModel.last_updated.desc()).first()
        return 0 if latest_nfc_tag is None else latest_nfc_tag.last_updated

    @staticmethod
    def get_number_of_nfc_tags():
        return db.session.query(func.count(NFCTagModel.id))

    @staticmethod
    def populate_from_dict(nfc_tag_dict):
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
        before = NFCTagStore.get_number_of_nfc_tags()
        def convert_one(k, v, curtime):
            id = k
            # these double-pops actually pull both of the keys from the dictionary;
            # this is intentional as we don't want them to stick around afterward
            name = v.pop("name", v.pop("_name", None))
            desc = v.pop("description", v.pop("desc", None))
            nfc_tag_type = v.pop("type", None)
            attr = json.dumps(v)
            return NFCTagModel(id=id, name=name, description=desc,
                type=nfc_tag_type, attr=attr, last_updated=curtime)

        cur_time = NFCTagStore.get_current_timestamp()
        for k, v in nfc_tag_dict.items():
            nfc_tag_model = convert_one(k, v, cur_time)
            db.session.add(nfc_tag_model)
        db.session.commit()

        after = NFCTagStore.get_number_of_nfc_tags()
        logger.info("added %s tags; before: %s, after: %s", len(nfc_tag_dict.items()), before, after)

    @staticmethod
    def get_current_timestamp():
        return int(time.time())

    @staticmethod    
    def get_all_nfc_tags():
        return NFCTagModel.query.all()

    @staticmethod    
    def get_nfc_tag_by_id(id):
        return NFCTagModel.query.filter(NFCTagModel.id == id).first()

    @staticmethod
    def delete_nfc_tag_by_id(id):
        to_delete = NFCTagModel.query.filter(NFCTagModel.id == id).first()
        db.session.delete(to_delete)
        db.session.commit()
        return True


TAG_REGISTRY_MAP = {
    "webhook": WebhookTag,
    "slack": SlackTag,
    "twinkly": TwinklyTag,
}

class NFCTagManager():
    # todo; merge this class with NFCTagStore
    def __init__(self, app_context=None):
        self.app_context = app_context
        self.nfc_tags_file = app_context.config.get("NFC_TAG_FILE")
        self.last_updated = -1
        self.tags = {}
        self._tags = {}

        if self.should_import_file():
            self.import_file()

    instance = None

    @classmethod
    def get_instance(cls, app_context=None):
        if cls.instance is None:
            cls.instance = NFCTagManager(app_context)
        return cls.instance


    def should_import_file(self):
        """
        This is not a super smart way of doing things, but it should work. tl;dr,
        if the modified time of the yaml file is more recent than the most recent
        modified time of any nfc_tag in the db, then we should update.

        *** note, this is destructive in nature; yaml will completely overwrite
        the database ***
        """
        if not os.path.isfile(self.nfc_tags_file):
            return False
        last_db_update = NFCTagStore.get_last_updated_time()
        last_file_update = int(os.stat(self.nfc_tags_file).st_mtime)
        logger.info("last db updated: %s, last file updated: %s", last_db_update, last_file_update)
        return last_file_update > last_db_update
    

    def import_file(self):
        with open(self.nfc_tags_file, 'r') as f:
            nfc_tag_defs = yaml.load(f, Loader=yaml.FullLoader)
        NFCTagStore.populate_from_dict(nfc_tag_defs)


    def nfc_tag_factory(self, id, data, nfc_tag_type=None, name=None, description=None):
        # TODO build a composite tag in case we want to do e.g. spotify + webhook;
        # perhaps do a list of types or something?

        # for this, we want the explicitly provided values to rule; those are the new
        # style of tags. However, we still need to have the old style around to work with
        if nfc_tag_type is None:
            nfc_tag_type = data.get("type")

        if nfc_tag_type is None or TAG_REGISTRY_MAP.get(nfc_tag_type) is None:
            if name is not None:
                data["name"] = name
            if description is not None:
                data["description"] = description
            return LegacyTag(id, **data)
        
        nfc_tag_class = TAG_REGISTRY_MAP.get(nfc_tag_type)
        return nfc_tag_class(id, app_context=self.app_context, **data)


    def get_nfc_tag_by_id(self, id):
        """
        Looks everywhere for a tag which is registered. Will return either
        old-style or new-style tags, depending on which store it comes from.
        New style will override old style
        """
        nfc_tag_model = NFCTagStore.get_nfc_tag_by_id(id)
        
        if nfc_tag_model is None:
            nfc_tag = UnknownTag(id)
        else:
            nfc_tag = self.nfc_tag_factory(id, nfc_tag_model.get_attr_object(),
                nfc_tag_type=nfc_tag_model.type, name=nfc_tag_model.name,
                description=nfc_tag_model.description
            )
        logger.info("built tag of type %s from info %s", type(nfc_tag), nfc_tag_model)
        return nfc_tag
    

    def delete_nfc_tag_by_id(self, id):
        if id is None:
            return
        success = NFCTagStore.delete_nfc_tag_by_id(id)
        socketio.emit("tag_deleted", {"tag_id": id})
        