import logging

from . import web
from ..spotify import SpotifyClientConfig, SpotifyClient, set_user
from flask import Blueprint, \
    current_app, \
    redirect, \
    render_template, \
    request, \
    session

logger = logging.Logger(__name__)

spotify_client_config = SpotifyClientConfig(current_app.config.get("CLIENT_ID"),
    current_app.config.get("CLIENT_SECRET"), current_app.config.get("REDIRECT_URI"))

spotify_client = SpotifyClient(client_config=spotify_client_config)

@web.route("/", methods=["GET"])
def main():
    user = session.get("user", None)
    if user == None:
        # Auto login
        return redirect("/login", 307)
    logger.info(user)
    # we have a user here
    set_user(user)
    spotify_client.set_current_user(user)
    return render_template("index.html", user=user)


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

    session["user"] = user.id

    logger.info("Spotify activated.")

    return redirect("/", 307)