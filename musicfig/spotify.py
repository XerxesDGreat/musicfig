#!/usr/bin/env python

import io
import logging
import os
import sqlite3
import tekore as tk
import threading
import unidecode

from .models import db, Song
from flask import Blueprint, request, render_template, \
                  session, redirect, current_app
from musicfig import lego
from urllib.request import urlopen

logger = logging.getLogger(__name__)

spotify = Blueprint('spotify', __name__)

conf = (current_app.config['CLIENT_ID'], 
        current_app.config['CLIENT_SECRET'], 
        current_app.config['REDIRECT_URI']
       )
cred = tk.Credentials(*conf)
tkspotify = tk.Spotify()
users = {}

current_dir = os.path.dirname(os.path.abspath(__file__))

cache_lock = threading.Lock()

last_played = 'unknown'
last_out = ''

# def init_cache():
#     """Use a database to store song meta data to reduce API calls.
#     """
#     global connection
#     global cursor
#     cache_dir = current_dir + '/.cache'
#     os.makedirs(cache_dir, exist_ok=True)
#     connection = sqlite3.connect(cache_dir + '/songs.db', check_same_thread=False)
#     cursor = connection.cursor()
#     cursor.execute("create table if not exists song \
#                         (id text, \
#                          image_url text, \
#                          artist text, \
#                          name text, \
#                          duration integer)")

def connectLego():
    legoThread = threading.Thread(target=lego.Base, args=(), kwargs={"app_context": current_app._get_current_object()})
    legoThread.daemon = True
    legoThread.start()

#init_cache()
connectLego()

def activated():
    try:
        user
    except NameError:
        return False
    else:
        return True

def pause():
    if conf[0] == '':
            return
    try:
        user
    except NameError:
        return
    if user_token(user) is None:
            logger.error('No Spotify token found.')
            return ''
    with tkspotify.token_as(users[user]):
        try:
            tkspotify.playback_pause()
        except Exception:
            pass

def resume():
    if conf[0] == '':
            return
    try:
        user
    except NameError:
        return 0
    if user_token(user) is None:
            logger.error('No Spotify token found.')
            return ''
    sp_remaining = 60000
    with tkspotify.token_as(users[user]):
        try:
            tkspotify.playback_resume()
            song = tkspotify.playback_currently_playing()
            #sp_elapsed = song.progress_ms
            #sp_id = song.item.id
            song_obj = Song.query.filter(Song.id == song.item.id).first()
            #cursor.execute("""select duration from song where id = ?;""", (sp_id,))
            sp_remaining = song_obj.duration_ms - song.progress_ms
        except Exception:
            pass
    return sp_remaining

def spotcast(spotify_uri,position_ms=0):
    """Play a track, playlist or album on Spotify.
    """
    global users
    global user
    if conf[0] == '':
            return 0
    try:
        user
    except NameError:
        logger.warn('Tag detected but Spotify is not activated. Please visit %s' % conf[2].replace('callback',''))
        return 0
    if user_token(user) is None:
            logger.error('No Spotify token found.')
            return 0
    uri = spotify_uri.split(':')
    with tkspotify.token_as(users[user]):
        try:
            if uri[0] == 'track':
                tkspotify.playback_start_tracks([uri[1]],position_ms=position_ms)
            else:
                tkspotify.playback_start_context('spotify:' + spotify_uri,position_ms=position_ms)
        except Exception as e:
            logger.error("Could not cast to Spotify.")
            logger.error(e)
            return -1
        try:
            song = Song.query.filter(Song.id == uri[1]).first() # ick at uri[1]
        except Exception as e:
            logger.error(e)
            song = None
            return 60000
        if song is None:
            return 60000
        artist = song.artist
        name = song.name
        duration_ms = song.duration_ms
        logger.info('Playing %s.' % name)
        return duration_ms
    return 0

def set_user(new_user):
    global user
    user = new_user

def get_user():
    global user
    return user

@spotify.route('/', methods=['GET'])
def main():
    global user
    user = session.get('user', None)
    if user == None:
        # Auto login
        return redirect('/login', 307)
    return render_template("index.html", user=user)

@spotify.route('/login', methods=['GET'])
def login():
    if conf[0] == '':
        session['user'] = 'local'
        return redirect('/', 307)
    else:
        auth_url = cred.user_authorisation_url(scope=tk.scope.every)
        return redirect(auth_url, 307)

@spotify.route('/callback', methods=['GET'])
def login_callback():
    global users
    code = request.args.get('code', None)

    token = cred.request_user_token(code)
    with tkspotify.token_as(token):
            info = tkspotify.current_user()

    session['user'] = info.id
    users[info.id] = token

    logger.info('Spotify activated.')

    return redirect('/', 307)

def user_token(user):
    if user == 'local':
       return None
    if user is not None:
        token = users[user]
        if token.is_expiring:
            token = cred.refresh(token)
            users[user] = token
        return users[user]
    else:
        return None

@spotify.route('/nowplaying')
def nowplaying():
    """Display the Album art of the currently playing song.
    """
    try:
        if user_token(user) is None:
            return ''
    except Exception:
        return ''
    global last_played
    global last_out
    with tkspotify.token_as(users[user]):
        try:
            song = tkspotify.playback_currently_playing()
        except Exception as e:
            logger.error('Spotify could not find any track playing: %s' % e)
            return render_template('nowplaying.html')
        if (song is None) or (not song.is_playing):
            return render_template('nowplaying.html')
        # The cache_lock avoids the "recursive use of cursors not allowed" exception.
        song_obj = None
        try:
            cache_lock.acquire(True)
            song_obj = Song.query.filter(Song.id == song.item.id).first()
        except Exception as e:
            logger.error("Could not query cache database: %s" % e)
            return render_template('nowplaying.html')
        finally:
            cache_lock.release()
        if song_obj is None:
            track = tkspotify.track(song.item.id)
            images_url = track.album.images
            image_url = images_url[0].url
            name = unidecode.unidecode(track.name)
            duration_ms = track.duration_ms
            artists = ''
            for item in track.artists:
                artists += unidecode.unidecode(item.name) + ', '
            artist = artists[:-2]
            song_obj = Song(
                id=song.item.id,
                image_url=image_url,
                artist=artist,
                name=name,
                duration_ms=duration_ms
            )
            db.session.add(song_obj)
            db.session.commit()
        out = last_out
        if song_obj.id != last_played:
          out = render_template("nowplaying.html", 
                               spotify_id=song_obj.id,
                               image_url=song_obj.image_url, 
                               artist=song_obj.artist, 
                               name=song_obj.name)
          last_played = song_obj.id
          last_out = out
        return out
