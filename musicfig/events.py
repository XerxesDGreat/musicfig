from flask_socketio import SocketIO
from . import socketio
from flask_socketio import send

@socketio.on('message')
def on_message(message):
    send(message)