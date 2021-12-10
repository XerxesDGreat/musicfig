import logging

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

    def send_new_tag_event(self, tag_id):
        emit('new_tag', {'id': id})