from flask import Blueprint, request, render_template, \
                  flash, g, session, redirect, url_for, \
                  current_app
from musicfig import spotify

jukebox = Blueprint('spotify', __name__)

@jukebox.route('/', methods=['GET'])
def main():
    user = session.get('user', None)
    spotify.set_user(user)
    if user == None:
        # Auto login
        return redirect('/login', 307)
    return render_template("index.html", user=user)