import logging

from .spotify import set_user
from flask import Blueprint, render_template, session, redirect

logger = logging.Logger(__name__)

web = Blueprint('web', __name__)

@web.route('/', methods=['GET'])
def main():
    user = session.get('user', None)
    if user == None:
        # Auto login
        return redirect('/login', 307)
    logger.info(user)
    # we have a user here
    set_user(user)
    return render_template("index.html", user=user)