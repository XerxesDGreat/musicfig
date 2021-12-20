import logging

# figure out how to make this a plugin, maybe

from . import web
from flask import \
    redirect, \
    render_template, \
    request, \
    session
from ..plugins.spotify import spotify_client

logger = logging.getLogger(__name__)

@web.route("/", methods=["GET"])
def main():
    user_id = session.get("user", None)
    if user_id == None:
        # Auto login
        return redirect("/login", 307)
    spotify_client.set_current_user_id(user_id)
    return render_template("index.html", user=user_id)


@web.route("/login", methods=["GET"])
def login():
    if spotify_client.get_client_id() is None:
        session["user"] = "local"
        auth_url = "/"
    else:
        auth_url = spotify_client.get_authorization_url()
    
    return redirect(auth_url, 307)


@web.route("/callback", methods=["GET"])
def login_callback():
    code = request.args.get("code", None)

    token = spotify_client.get_user_token_for_code(code)
    user = spotify_client.get_user_from_token(token)
    logger.info(user)

    session["user"] = user.id

    logger.info("Spotify activated.")

    return redirect("/", 307)

    
@web.route('/nowplaying')
def nowplaying():
    """
    Display the Album art of the currently playing song.
    """
    default_template = "nowplaying.html"
    if spotify_client.get_current_user_token(refresh=True) is None:
        logger.info("no token for user")
        return render_template(default_template, status="no token")

    song, _ = spotify_client.get_currently_playing()
    if song is None:
        return render_template(default_template, status="nothing currently playing")
    
    return render_template(default_template,
        spotify_id=song.id,
        image_url=song.image_url,
        artist=song.artist,
        name=song.name
    )