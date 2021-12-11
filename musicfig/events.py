import logging

from . import socketio
from .nfc_tag import NFCTagManager
from flask import current_app
from flask_socketio import Namespace, emit

logger = logging.getLogger(__name__)

nfc_tag_manager = NFCTagManager.get_instance(current_app)

class NFCTagHandler(Namespace):
    def on_connect(self):
        logger.info("socketio connected")
        emit('connect_happy', {"foo": "bar"})
    
    def on_disconnect(self):
        logger.info("socketio disconnected")
        emit('disconnect_happy', {"fob": "bazzz"})
    
    def on_comm(self, data):
        logger.info("socketio comm: %s", data)

    def on_json(self, data):
        logger.info("incoming json information: %s", data)
    
    def on_do_tag_delete(self, data):
        logger.info("incoming tag delete event: %s", data)
        tag_id = data.get("tag_id")
        if tag_id is None:
            logger.error("attempted to delete tag without passing a tag id: %s", data)
            return
        nfc_tag_manager.delete_nfc_tag_by_id(tag_id)