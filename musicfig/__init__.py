#!/usr/bin/env python
import os
import logging

from flask import Flask, render_template
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from logging.config import dictConfig

dictConfig({
    'version': 1,
    'formatters': {'default': {
        'format': '[%(asctime)s] %(levelname)s: %(message)s',
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

db = SQLAlchemy()
socketio = SocketIO()

from . import models
from . import events

def init_app():
    app = Flask(__name__,
                static_url_path='', 
                static_folder='templates')
    app.config.from_object('config')

    db.init_app(app)
    socketio.init_app(app)

    @app.errorhandler(404)
    def not_found(error):
        return render_template('404.html'), 404

    with app.app_context(), app.test_request_context():
        from musicfig.spotify import spotify as spotify_module
        app.register_blueprint(spotify_module)

        from musicfig.nfc_tag import nfc_tag as nfc_tag_module
        app.register_blueprint(nfc_tag_module)

        db.create_all()

        #from musicfig.nfc_tag import tag as tag_module
        #app.register_blueprint(tag_module, url_prefix="tag")
        logger.info('Musicfig %s started.' % app_version)
        if app.config['CLIENT_ID']:
            logger.info('To activate Spotify visit: %s' % app.config['REDIRECT_URI'].replace('callback',''))

    return app
