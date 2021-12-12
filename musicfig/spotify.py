#!/usr/bin/env python

import logging
import tekore as tk
import unidecode

from .models import db, Song
from collections import namedtuple
from tekore._convert import to_uri
from tekore._error import HTTPError

logger = logging.getLogger(__name__)

ONE_MINUTE_IN_MS = 60 * 1000 # 60 seconds

SpotifyClientConfig = namedtuple("SpotifyClientConfig", ["client_id", "client_secret", "redirect_uri"])

class SpotifyClient:

    _client = None

    @classmethod
    def get_client(cls, client_config=None):
        if cls._client is None:
            cls._client = SpotifyClient(client_config)
        return cls._client

    def __init__(self, client_config=None):
        self.current_user_id = None
        self.user_token_map = {"local": None} # `local` is apparently a special user with no token; keep it
        self.config = client_config
        self.credentials = None
        self.client = None
        self._init_client()

    ###############################
    # client configuration operations
    ###############################
    def _init_client(self):
        self.credentials = tk.Credentials(self.config.client_id, self.config.client_secret, self.config.redirect_uri)
        self.client = tk.Spotify()
    
    def get_client_id(self):
        return self.credentials.client_id

    def get_authorization_url(self):
        return self.credentials.user_authorisation_url(scope=tk.scope.every)

    def is_activated(self):
        return self.current_user_id is not None
    
    def is_configured(self):
        return self.config is not None and self.get_client_id() is not None

    ###############################
    # User operations
    ###############################
    def get_current_user_id(self):
        return self.current_user_id

    def get_current_user_token(self, refresh=False):
        token = self.user_token_map.get(self.current_user_id)
        if token is None:
            return token

        if token.is_expiring and refresh:
            try:
                token = self.credentials.refresh(token)
            except HTTPError as e:
                logger.exception("failed refreshing token: %s", str(e))
            self.user_token_map[self.current_user_id] = token
        return token
    
    def set_current_user_id(self, user):
        self.current_user_id = user
        logger.info(self.current_user_id)
    
    def get_user_token_for_code(self, code):
        return self.credentials.request_user_token(code)
    
    def get_user_from_token(self, token):
        with self.client.token_as(token):
            user = self.client.current_user()
        self.user_token_map[user.id] = token
        return user
    
    ###############################
    # Playback operations
    ###############################
    def get_currently_playing(self):
        currently_playing = self.get_current_users_current_playing()
        if currently_playing is None:
            return None, None

        return self._get_song_from_track(currently_playing.item), currently_playing
    
    def _get_song_from_track(self, track):
        """
        This mainly converts the Track object into a Song object, caching if necessary
        """
        try:
            song = Song.query.filter(Song.id == track.id).first()
        except Exception as e:
            logger.exception("Song query failed: %s", str(e))
            song = None
        
        if song is None:
            song = self._create_song_object_from_track(track)

        return song
        
    def _create_song_object_from_track(self, track):
        image_url = track.album.images[0].url # get the first image from the list of potentials
        name = unidecode.unidecode(track.name)
        duration_ms = track.duration_ms
        artist = ",".join([unidecode.unidecode(a.name) for a in track.artists])
        song = Song(id=track.id, image_url=image_url, artist=artist, name=name, duration_ms=duration_ms)
        db.session.add(song)
        db.session.commit()
        return song
    
    def get_current_users_current_playing(self):
        token = self.get_current_user_token()
        with self.client.token_as(token):
            try:
                currently_playing = self.client.playback_currently_playing()
            except HTTPError as e:
                logger.exception("Could not find any track playing: %s", str(e))
                return None

        if currently_playing is None or not currently_playing.is_playing:
            return None

        return currently_playing if currently_playing is not None and currently_playing.is_playing else None
    
    def _get_token_and_verify_active_and_configured(self):
        if not self.is_activated() or not self.is_configured():
            return
        
        token = self.get_current_user_token()
        if token is None:
            logger.error("No Spotify token found")
            return

        return token 

    def pause(self):
        token = self._get_token_and_verify_active_and_configured()
        if token is None:
            return
        
        with self.client.token_as(token):
            try:
                self.client.playback_pause()
            except HTTPError as e:
                logger.exception("Failed pausing playback: %s", str(e))
    
    def resume(self):
        token = self._get_token_and_verify_active_and_configured()
        if token is None:
            return
        
        ms_remaining_in_song = ONE_MINUTE_IN_MS
        with self.client.token_as(token):
            try:
                self.client.playback_resume()
                song, currently_playing = self.get_currently_playing()
                ms_remaining_in_song = song.duration_ms - currently_playing.progress_ms
            except HTTPError as e:
                logger.exception("Failed resuming playback: %s", str(e))
                logger.info("finding more devices")
                devices = self.client.playback_devices()
                logger.info(devices)

        return ms_remaining_in_song
    
    def spotcast(self, spotify_uri, position_ms=0):
        """
        Returns the duration in ms... or at least, attempts to. If it's not a song,
        just returns one minute
        """
        token = self._get_token_and_verify_active_and_configured()
        if token is None:
            return
        media_type, media_id = spotify_uri.split(":")
        with self.client.token_as(token):
            try:
                if media_type == "track":
                    self.client.playback_start_tracks([media_id], position_ms=position_ms)
                else:
                    self.client.playback_start_context(to_uri(media_type, media_id))
                logger.info("started playing media identified by %s", spotify_uri)
            except HTTPError as e:
                logger.exception("Failed spotcast with uri: %s due to error: %s", spotify_uri, str(e))
                return
        
        if media_type != "track":
            return ONE_MINUTE_IN_MS
        
        song, _ = self.get_currently_playing()
        if song is None:
            return ONE_MINUTE_IN_MS

        return song.duration_ms