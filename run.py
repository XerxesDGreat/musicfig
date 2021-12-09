#!/usr/bin/env python
# this is no longer being used to control running of the and will be removed

from musicfig import init_app

app = init_app()

app.run(host='0.0.0.0', port=5000, debug=True)
