import json
import logging
import os
import time
import yaml


from .socketio import socketio
from .models import db, NFCTagModel
from flask import current_app
from musicfig import colors
from sqlalchemy import func

logger = logging.getLogger(__name__)

# all uses of current_app in here are for config; try just passing those
# config values, mayhap?

class NFCTagOperationError(BaseException):
    pass

class NFCTag():
    @classmethod
    def get_friendly_name(cls):
        """
        hacky - but effective - way to get the friendly name of this class.

        Brittle because it assumes the class name ends in "Tag"

        Override if not working
        """
        return cls.__name__[0:-3].lower()
    
    @classmethod
    def _get_required_attributes(cls):
        return cls.required_attributes if hasattr(cls, 'required_attributes') else []
    
    @classmethod
    def get_attributes_description(cls):
        json_content = ",".join(['"%s": "..."' % att for att in cls._get_required_attributes()])
        return "{%s}" % json_content

    def __init__(self, identifier, name=None, description=None, attributes={}, **kwargs):
        self.identifier = identifier
        self.name = name
        self.description = description
        self.attributes = attributes
        self.logger = logging.getLogger("musicfig")
        self._init_attributes()
    
    def _init_attributes(self):
        self._verify_attributes()

    def _verify_attributes(self):
        # unclear if this will work...
        for required_attribute in self._get_required_attributes():
            if required_attribute not in self.attributes:
                raise KeyError("missing required key '%s'" % required_attribute)
    
    def get_type(self):
        return self.__class__.__name__.lower().replace("Tag", "")

    def on_add(self):
        pass

    def on_remove(self):
        pass
    
    def get_pad_color(self):
        return colors.OFF

    def should_do_light_show(self):
        return True

    def should_use_class_based_execution(self):
        return True


class UnregisteredTag(NFCTag):
    """
    This is used for tags which have not been added to the database
    """
    def on_add(self):
        super().on_add()
        # should _probably_ use a logger which is associated with the
        # app, but this is fine for now. Maybe
        logger.info('Discovered new tag: %s' % self.identifier)
        socketio.emit("new_tag", {"tag_id": self.identifier})

    def get_pad_color(self):
        return colors.RED


class UnknownTypeTag(NFCTag):
    """
    This is used in cases where tags are persisted to the database but then a plugin is removed
    or unregistered; those orphan tags will be represented by this type
    """

    def get_pad_color(self):
        return colors.RED

    def should_use_class_based_execution(self):
        return False


class NFCTagStore():
    tag_cache = {}

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
    
    @staticmethod
    def create_nfc_tag(id, type, name=None, description=None, attributes=None):
        model = NFCTagModel(id=id, name=name, description=description, type=type,
                            attr=attributes, last_updated=NFCTagStore.get_current_timestamp())
        db.session.add(model)
        db.session.commit()
        return model


class NFCTagManager():
    # todo; merge this class with NFCTagStore
    def __init__(self):
        self.nfc_tags_file = current_app.config.get("NFC_TAG_FILE")
        self.last_updated = -1
        self.tags = {}
        self._tags = {}

        if self.should_import_file():
            self.import_file()

    instance = None

    @classmethod
    def get_instance(cls):
        if cls.instance is None:
            cls.instance = NFCTagManager()
        return cls.instance
    
    TAG_REGISTRY_MAP = {}
    
    @classmethod
    def register_tag_type(cls, nfc_tag_class):
        if not issubclass(nfc_tag_class, NFCTag):
            raise TypeError("`nfc_tag_class` must be a class object which extends NFCTag")
        cls.TAG_REGISTRY_MAP[nfc_tag_class.get_friendly_name()] = nfc_tag_class
    
    @classmethod
    def get_tag_class_from_tag_type(cls, nfc_tag_type: str):
        return cls.TAG_REGISTRY_MAP.get(nfc_tag_type, UnknownTypeTag)
    
    @classmethod
    def get_registered_tag_types(cls):
        """
        Fetches a dictionary of all the registered tag types in the format `type_str` -> `type_class_obj`

        Note 
        """
        return cls.TAG_REGISTRY_MAP

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


    def nfc_tag_from_model(self, nfc_tag_model):
        # TODO build a composite tag in case we want to do e.g. spotify + webhook;
        # perhaps do a list of types or something?

        nfc_tag_class = NFCTagManager.get_tag_class_from_tag_type(nfc_tag_model.type)
        return nfc_tag_class(nfc_tag_model.id,
                             name=nfc_tag_model.name,
                             description=nfc_tag_model.description,
                             attributes=nfc_tag_model.get_attr_object()
                             )


    def get_nfc_tag_by_id(self, id):
        """
        Looks everywhere for a tag which is registered. Will return either
        old-style or new-style tags, depending on which store it comes from.
        New style will override old style
        """
        if id not in self.tags:
            nfc_tag_model = NFCTagStore.get_nfc_tag_by_id(id)
            
            if nfc_tag_model is None:
                nfc_tag = UnregisteredTag(id)
            else:
                nfc_tag = self.nfc_tag_from_model(nfc_tag_model)
            logger.debug("built tag of type %s from info %s", type(nfc_tag), nfc_tag_model)
            self.tags[id] = nfc_tag
        return self.tags.get(id)
    

    def delete_nfc_tag_by_id(self, id):
        if id is None:
            return
        try:
            self.tags.pop(id)
        except Exception:
            pass
        success = NFCTagStore.delete_nfc_tag_by_id(id)
        socketio.emit("tag_deleted", {"tag_id": id})
    

    def create_nfc_tag(self, id, tag_type, name=None, description=None, attributes=None):
        if id is None or tag_type is None:
            raise ValueError("must include both id and tag_type")
        if NFCTagManager.get_tag_class_from_tag_type(tag_type) is UnknownTypeTag:
            raise ValueError("tag_type was %s, must be one of the following: [%s]",
                                tag_type, "],[".join(NFCTagManager.get_registered_tag_types().keys()))
        if isinstance(attributes, dict):
            attributes = json.dumps(dict)

        model_obj = NFCTagStore.create_nfc_tag(id, tag_type, name, description, attributes)
        nfc_tag = self.nfc_tag_from_model(model_obj)
        self.tags[id] = nfc_tag
        return nfc_tag