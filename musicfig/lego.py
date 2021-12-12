#!/usr/bin/env python

from . import socketio, mp3player, spotify
from .spotify import SpotifyClientConfig, SpotifyClient
from collections import namedtuple
from flask import current_app
from musicfig import colors, webhook
from mutagen.mp3 import MP3
from musicfig.nfc_tag import LegacyTag, NFCTagManager, NFCTag, SpotifyTag

import binascii
import glob
import logging
import os
import random
import signal
import threading
import time
import usb.core
import usb.util

logger = logging.getLogger(__name__)

# class Pad():
#     def __init__(self, id):
#         self.id = id
#         self.nfc_tag_list = {}
    
    
#     def add_nfc_tag(self, identifier, nfc_tag):
#         self.nfc_tag_list.set(identifier, nfc_tag)
    

#     def remove_nfc_tag_by_id(self, identifier):
#         self.nfc_tag_list.pop(identifier)


# named tuple allows for less string parsing and guessing what goes where
DimensionsTagEvent = namedtuple("DimensionsTagEvent", ["was_removed", "pad_num", "identifier"])


class Dimensions():

    def __init__(self):
        try:
           self.dev = self.init_usb()
        except Exception as e:
            logging.info("failed initialization: %s", e)
            return

    def init_usb(self):
        dev = usb.core.find(idVendor=0x0e6f, idProduct=0x0241)

        if dev is None:
            logger.error('Lego Dimensions pad not found')
            raise ValueError('Device not found')

        if dev.is_kernel_driver_active(0):
            dev.detach_kernel_driver(0)

        # Initialise portal
        dev.set_configuration()
        dev.write(1,[0x55, 0x0f, 0xb0, 0x01, 0x28, 0x63, 0x29, 0x20, 0x4c, 
                     0x45, 0x47, 0x4f, 0x20, 0x32, 0x30, 0x31, 0x34, 0xf7, 
                     0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
                     0x00, 0x00, 0x00, 0x00, 0x00])
        return dev

    def send_command(self, command):
        checksum = 0
        for word in command:
            checksum = checksum + word
            if checksum >= 256:
                checksum -= 256
            message = command+[checksum]

        while(len(message) < 32):
            message.append(0x00)

        try:
            self.dev.write(1, message)
        except Exception as e:
            logging.info("exception: %s", e)
            pass

    def change_pad_color(self, pad, colour):
        self.send_command([0x55, 0x06, 0xc0, 0x02, pad, colour[0], 
                          colour[1], colour[2],])
        return

    def fade_pad_color(self, pad, pulse_time, pulse_count, colour):
        self.send_command([0x55, 0x08, 0xc2, 0x0f, pad, pulse_time, 
                          pulse_count, colour[0], colour[1], colour[2],])
        return

    def flash_pad_color(self, pad, on_length, off_length, pulse_count, colour):
        self.send_command([0x55, 0x09, 0xc3, 0x03, pad, 
                          on_length, off_length, pulse_count, 
                          colour[0], colour[1], colour[1],])
        return

    def get_tag_event(self):
        try:
            inwards_packet = self.dev.read(0x81, 32, timeout = 10)
            bytelist = list(inwards_packet)
            if not bytelist:
                return
            if bytelist[0] != 0x56:
                return
            pad_num = bytelist[2]
            uid_bytes = bytelist[6:13]
            identifier = binascii.hexlify(bytearray(uid_bytes)).decode("utf-8")
            identifier = identifier.replace('000000','')
            removed = bool(bytelist[5])
            return DimensionsTagEvent(removed, pad_num, identifier)
        except Exception:
            return


class Base():
    def __init__(self):
        # self.OFF   = [0,0,0]
        # self.RED   = [100,0,0]
        # self.GREEN = [0,100,0]
        # self.BLUE  = [0,0,100]
        # self.PINK = [100,75,79]
        # self.ORANGE = [100,64,0]
        # self.PURPLE = [100,0,100]
        # self.LBLUE = [100,100,100]
        # self.OLIVE = [50,50,0]
        # self.COLOURS = ['self.RED', 'self.GREEN', 'self.BLUE', 'self.PINK', 
        #                 'self.ORANGE', 'self.PURPLE', 'self.LBLUE', 'self.OLIVE']
                        
        self._init_spotify()
        self.base = self.startLego()

    def _init_spotify(self):
        cur_obj = current_app._get_current_object()
        config = cur_obj.config
        spotify_client_config = SpotifyClientConfig(config.get("CLIENT_ID"),
            config.get("CLIENT_SECRET"), config.get("REDIRECT_URI"))

        self.spotify_client = SpotifyClient.get_client(client_config=spotify_client_config)

    # def randomLightshow(self,duration = 60):
    #     logger.info("Lightshow started for %s seconds." % duration)
    #     self.lightshowThread = threading.currentThread()
    #     t = time.perf_counter()
    #     while getattr(self.lightshowThread, "do_run", True) and (time.perf_counter() - t) < duration:
    #         pad = random.randint(0,2)
    #         self.colour = random.randint(0,len(self.COLOURS)-1)
    #         self.base.change_pad_color(pad,eval(self.COLOURS[self.colour]))
    #         time.sleep(round(random.uniform(0,0.5), 1))
    #     self.base.change_pad_color(0,self.OFF)

    # def startLightshow(self,duration_ms):
    #     if switch_lights:
    #         self.lightshowThread = threading.Thread(target=self.randomLightshow,
    #             args=([(duration_ms / 1000)]))
    #         self.lightshowThread.daemon = True
    #         self.lightshowThread.start()

    def initMp3(self):
        self.p = mp3player.Player()
        def monitor():
            global mp3state
            global mp3elapsed
            while True:
                state = self.p.event_queue.get(block=True, timeout=None)
                mp3state = str(state[0]).replace('PlayerState.','')
                mp3elapsed = state[1]
            logger.info('thread exited.')
        threading.Thread(target=monitor, name="monitor").daemon = True
        threading.Thread(target=monitor, name="monitor").start() 

    def startMp3(self, filename, mp3_dir, is_playlist=False):
        global mp3_duration
        # load an mp3 file
        if not is_playlist:
            mp3file = mp3_dir + filename
            logger.info('Playing %s.' % filename)
            self.p.open(mp3file)
            self.p.play()

            audio = MP3(mp3file)
            mp3_duration = audio.info.length
            #self.startLightshow(mp3_duration * 1000)
        else:
            self.p.playlist(filename)
            mp3_duration = 0
            if filename:
                for file_mp3 in filename:
                    audio = MP3(file_mp3)
                    mp3_duration = mp3_duration + audio.info.length
            else:
                logger.info('Check the folder, maybe empty!!!')
            #self.startLightshow(mp3_duration * 1000)

    def stopMp3(self):
        global mp3state
        try:
            #self.p.stop()
            mp3state = 'STOPPED'
        except Exception:
            pass

    def pauseMp3(self):
        global mp3state
        if 'PLAYING' in mp3state:
            self.p.pause()
            logger.info('Track paused.')
            mp3state = 'PAUSED'
            return

    def playMp3(self, filename, mp3_dir):
        global t
        global mp3state
        self.spotify_client.pause()
        if previous_tag == current_tag and 'PAUSED' in ("%s" % mp3state):
            # Resume
            logger.info("Resuming mp3 track.")
            self.p.play()
            remaining = mp3_duration - mp3elapsed
            if remaining >= 0.1:
                self.startLightshow(remaining * 1000)
                return
        # New play 
        self.stopMp3()
        self.startMp3(filename, mp3_dir)
        mp3state = 'PLAYING'

    def playPlaylist(self, playlist_filename, mp3_dir, shuffle=False):
        global mp3state
        list_mp3_to_play = []
        self.spotify_client.pause()

        mp3list = mp3_dir +'/'+ playlist_filename + '/*.mp3'
        ##logger.debug(mp3list)

        list_mp3_to_play = glob.glob(mp3list)

        if shuffle:
            random.shuffle(list_mp3_to_play)
        ##logger.debug(list_mp3_to_play)

        self.startMp3(list_mp3_to_play, mp3_dir, True)
        mp3state = 'PLAYING'

    def startLego(self):
        global current_tag
        global previous_tag
        global mp3state
        global p
        #global switch_lights
        current_tag = None
        previous_tag = None
        mp3state = None
        nfc = NFCTagManager.get_instance()
        self.base = Dimensions()
        logger.info("Lego Dimensions base activated.")
        self.initMp3()
        #switch_lights = current_app.config["RUN_LIGHT_SHOW_DEFAULT"]
        #logger.info('Lightshow is %s' % switch_lights) #("disabled", "enabled")[switch_lights])
        self.base.change_pad_color(0, colors.DIM)
        # if switch_lights:
        #     self.base.change_pad_color(0,self.GREEN)
        # else:
        #     self.base.change_pad_color(0,self.OFF)

        i = 0
        while True:
            i = i + 1
            if i == 10000:
                logging.info("loop")
                i = 0
            tag_event = self.base.get_tag_event()
            if not tag_event:
                continue

            # status = tag.split(':')[0]
            # pad = int(tag.split(':')[1])
            # identifier = tag.split(':')[2]
            logging.info(tag_event)

            if tag_event.was_removed:
                self.base.change_pad_color(pad=tag_event.pad_num, colour=colors.DIM)
                if tag_event.identifier == current_tag:
                    # try:
                    #     self.lightshowThread.do_run = False
                    #     self.lightshowThread.join()
                    # except Exception:
                    #     pass
                    self.pauseMp3()
                    if self.spotify_client.is_activated():
                        self.spotify_client.pause()
                elif isinstance(current_tag, SpotifyTag) and tag_event.identifier == current_tag.identifier:
                    self.pauseMp3()
                    if self.spotify_client.is_activated():
                        self.spotify_client.pause()
            else:
                self.base.change_pad_color(pad=tag_event.pad_num, colour=colors.BLUE)

                mp3_dir = current_app.config["MP3_DIR"]
                ##logger.debug(mp3_dir)

                # Stop any current songs and light shows
                # try:
                #     self.lightshowThread.do_run = False
                #     self.lightshowThread.join()
                # except Exception:
                #     pass

                # nfc_tag could be a dict or an NFCTag object
                nfc_tag = nfc.get_nfc_tag_by_id(tag_event.identifier)
                logging.info(nfc_tag)

                previous_tag = current_tag
                current_tag = nfc_tag.identifier

                if nfc_tag.should_use_class_based_execution():
                    logging.info("doing new")
                    nfc_tag.on_add()
                    #self.base.fade(tag_event.pad_num, nfc_tag.get_pad_color())
                    # Unknown tag. Display UID.
                
                else:
                    if isinstance(nfc_tag, SpotifyTag):
                        logger.info("spotify tag")
                        if self.spotify_client.is_activated():
                            logger.info("activated")
                            if current_tag == previous_tag:
                                self.spotify_client.resume()
                                #self.startLightshow(self.spotify_client.resume())
                                continue
                            self.stopMp3()
                            duration_ms = self.spotify_client.spotcast(nfc_tag.spotify_uri, nfc_tag.start_position_ms)
                            # if duration_ms > 0:
                            #     self.startLightshow(duration_ms)
                            #else:
                            # self.base.flash_pad_color(pad=tag_event.pad_num, on_length=10,
                            #     off_length=10, pulse_count=2, colour=self.RED)
                        else: 
                            logger.info("not activated")
                            current_tag = previous_tag

                            #https://open.spotify.com/playlist/6VdvufagCnB6BS52MxwPRw?si=9718899179eb413e
                    
                    else:
                    
                        nfc_tag = nfc_tag.definition

                        logging.info("doing old: %s", nfc_tag)
                        # if current_tag == None:
                        #     previous_tag = tag_event.identifier
                        # else:
                        # A tag has been matched
                        if 'playlist' in nfc_tag:
                            playlist = nfc_tag['playlist']
                            if 'shuffle' in nfc_tag:
                                shuffle = True
                            else:
                                shuffle = False
                            self.playPlaylist(playlist, mp3_dir, shuffle)
                        if 'mp3' in nfc_tag:
                            filename = nfc_tag['mp3']
                            self.playMp3(filename, mp3_dir)
                        if 'command' in nfc_tag:
                            command = nfc_tag['command']
                            logger.info('Running command %s' % command)
                            os.system(command)
                    
