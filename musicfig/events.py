import logging

from . import socketio
from flask_socketio import Namespace, emit

logger = logging.getLogger(__name__)

class TagNamespace(Namespace):
    def on_connect(self):
        logger.info("socketio connected")
        emit('connect_happy', {"foo": "bar"})
    
    def on_disconnect(self):
        logger.info("socketio disconnected")
        emit('disconnect_happy', {"fob": "bazzz"})
    
    def on_comm(self, data):
        logger.info("socketio comm: %s", data)

    def publish_new_tag_event(self, id):
        socketio.emit('new_tag', {"id": id})

    def on_json(self, data):
        logger.info("incoming json information: %s", data)
    
    def on_tag_delete(self, data):
        logger.info("incoming tag delete event: %s", data)