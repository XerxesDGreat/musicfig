#!/usr/bin/env python
from musicfig import init_app, socketio

app = init_app()

socketio.run(app, host='0.0.0.0', port=5000, debug=True)
