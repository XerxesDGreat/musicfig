#!/usr/bin/env python
import os
import logging

from .database import db
from .lego import DimensionsLoop
from .socketio import socketio
from .plugins import spotify_client, twinkly_plugin
from flask import Flask, render_template
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from logging.config import dictConfig
from pubsub import pub
from threading import Thread

dictConfig({
    'version': 1,
    'formatters': {'default': {
        'format': '[%(asctime)s] (%(filename)s:%(lineno)s) %(levelname)s: %(message)s',
    }},
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'default',
            'stream': 'ext://sys.stdout',
        },
        'logfile': {
            'level': 'INFO',
            'formatter': 'default',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'musicfig.log',
            'mode': 'a',
            'maxBytes': 1048576,
            'backupCount': 10
        }
    },
    'root': {
        'level': 'INFO',
        'handlers': ['console','logfile']
    }
})

logging.getLogger('werkzeug').disabled = True
print(__name__)
logger = logging.getLogger(__name__)
os.environ['WERKZEUG_RUN_MAIN'] = 'true'

# Check for updates
# stream = os.popen('git tag 2>/dev/null | tail -n 1')
# app_version = stream.read().split('\n')[0]
# if app_version == '':
#     app_version = "(offline mode)"

# VERSION_URL = "https://api.github.com/repos/XerxesDGreat/jukebox-portal/releases"
# try:
#     url = requests.get(VERSION_URL)
#     latest_version = url.json()[0]['tag_name']

#     if latest_version != app_version:
#       logger.info('Update %s available. Run install.sh to update.' % latest_version)
# except Exception:
#     pass
app_version = "heavy development"

# this is where you will put all your plugins
plugins = [
    spotify_client,
    twinkly_plugin
]

#socketio = SocketIO()
lego_thread = DimensionsLoop()

from . import models
#from . import events

def l(tag_event, nfc_tag):
    logger.info("%s, %s", tag_event, nfc_tag)

pub.subscribe(l, 'tag.added')
pub.subscribe(l, 'tag.removed')

def init_app():
    app = Flask(__name__,
                static_url_path='', 
                static_folder='templates')
    app.config.from_object('config')

    db.init_app(app)
    socketio.init_app(app)
    lego_thread.init_app(app)

    # Initializes all of the plugins. Any registration of models, attaching
    # of listeners, etc. should be done within each plugins' `init_app()`
    for plugin in plugins:
        plugin.init_app(app)

    @app.errorhandler(404)
    def not_found(error):
        return render_template('404.html'), 404

    with app.app_context(), app.test_request_context():
        from .web import web as web_blueprint
        app.register_blueprint(web_blueprint)

        db.create_all()
        lego_thread.daemon = True
        lego_thread.start()

        from .events import NFCTagHandler
        socketio.on_namespace(NFCTagHandler())

        logger.info('Musicfig %s started.' % app_version)
        if app.config['CLIENT_ID']:
            logger.info('To activate Spotify visit: %s' % app.config['REDIRECT_URI'].replace('callback',''))

    return app