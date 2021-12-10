import logging

from flask_socketio import SocketIO
from . import socketio
from flask_socketio import send

logger = logging.getLogger(__name__)

@socketio.on('message')
def on_message(message):
    logger.info("fasdfasdfasdfasdfasdfasdf")
    send(message)