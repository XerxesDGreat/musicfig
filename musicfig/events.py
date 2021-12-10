import logging

from flask_socketio import Namespace, emit

logger = logging.getLogger(__name__)

class TagNamespace(Namespace):
    def on_connect(self):
        logger.info("socketio connected")
    
    def on_disconnect(self):
        logger.info("socketio disconnected")
    
    def on_comm(self, data):
        logger.info("socketio comm: %s", data)