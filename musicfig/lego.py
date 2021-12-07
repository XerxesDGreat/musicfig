#!/usr/bin/env python

from collections import namedtuple
from flask import current_app
from musicfig import webhook
from mutagen.mp3 import MP3

import binascii
import glob
import logging
import musicfig.mp3player as mp3player
import musicfig.spotify as spotify
import musicfig.tags as nfctags
import os
import random
import threading
import time
import usb.core
import usb.util

logger = logging.getLogger(__name__)

class Pad():
    def __init__(self, id):
        self.id = id
        self.nfc_tag_list = {}
    
    
    def add_nfc_tag(self, identifier, nfc_tag):
        self.nfc_tag_list.set(identifier, nfc_tag)
    

    def remove_nfc_tag_by_id(self, identifier):
        self.nfc_tag_list.pop(identifier)


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

    def switch_pad(self, pad, colour):
        self.send_command([0x55, 0x06, 0xc0, 0x02, pad, colour[0], 
                          colour[1], colour[2],])
        return

    def fade_pad(self, pad, pulse_time, pulse_count, colour):
        self.send_command([0x55, 0x08, 0xc2, 0x0f, pad, pulse_time, 
                          pulse_count, colour[0], colour[1], colour[2],])
        return

    def flash_pad(self, pad, on_length, off_length, pulse_count, colour):
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
    def __init__(self, app):
        self.OFF   = [0,0,0]
        self.RED   = [100,0,0]
        self.GREEN = [0,100,0]
        self.BLUE  = [0,0,100]
        self.PINK = [100,75,79]
        self.ORANGE = [100,64,0]
        self.PURPLE = [100,0,100]
        self.LBLUE = [100,100,100]
        self.OLIVE = [50,50,0]
        self.COLOURS = ['self.RED', 'self.GREEN', 'self.BLUE', 'self.PINK', 
                        'self.ORANGE', 'self.PURPLE', 'self.LBLUE', 'self.OLIVE']
        self.app = app
        self.base = self.startLego()

    def randomLightshow(self,duration = 60):
        logger.info("Lightshow started for %s seconds." % duration)
        self.lightshowThread = threading.currentThread()
        t = time.perf_counter()
        while getattr(self.lightshowThread, "do_run", True) and (time.perf_counter() - t) < duration:
            pad = random.randint(0,2)
            self.colour = random.randint(0,len(self.COLOURS)-1)
            self.base.switch_pad(pad,eval(self.COLOURS[self.colour]))
            time.sleep(round(random.uniform(0,0.5), 1))
        self.base.switch_pad(0,self.OFF)

    def startLightshow(self,duration_ms):
        if switch_lights:
            self.lightshowThread = threading.Thread(target=self.randomLightshow,
                args=([(duration_ms / 1000)]))
            self.lightshowThread.daemon = True
            self.lightshowThread.start()

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
            self.startLightshow(mp3_duration * 1000)
        else:
            self.p.playlist(filename)
            mp3_duration = 0
            if filename:
                for file_mp3 in filename:
                    audio = MP3(file_mp3)
                    mp3_duration = mp3_duration + audio.info.length
            else:
                logger.info('Check the folder, maybe empty!!!')
            self.startLightshow(mp3_duration * 1000)

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
        spotify.pause()
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
        spotify.pause()

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
        global switch_lights
        current_tag = None
        previous_tag = None
        mp3state = None
        nfc = nfctags.Tags()
        self.base = Dimensions()
        logger.info("Lego Dimensions base activated.")
        self.initMp3()
        switch_lights = self.app.config["RUN_LIGHT_SHOW_DEFAULT"]
        logger.info('Lightshow is %s' % switch_lights) #("disabled", "enabled")[switch_lights])
        if switch_lights:
            self.base.switch_pad(0,self.GREEN)
        else:
            self.base.switch_pad(0,self.OFF)

        i = 0
        while True:
            i = i + 1
            if i == 1000:
                logging.info("loop")
                i = 0
            tag_event = self.base.get_tag_event()
            if not tag_event:
                pass

            # status = tag.split(':')[0]
            # pad = int(tag.split(':')[1])
            # identifier = tag.split(':')[2]
            logging.info(tag_event)

            if tag_event.was_removed:
                if tag_event.identifier == current_tag:
                    try:
                        self.lightshowThread.do_run = False
                        self.lightshowThread.join()
                    except Exception:
                        pass
                    self.pauseMp3()
                    if spotify.activated():
                        spotify.pause()
            else:
                if switch_lights:
                    self.base.switch_pad(pad = tag_event.pad_num, colour = self.BLUE)

                # Reload the tags config file
                nfc.load_tags()
                tags = nfc.tags
                mp3_dir = current_app.config["MP3_DIR"]
                ##logger.debug(mp3_dir)

                # Stop any current songs and light shows
                try:
                    self.lightshowThread.do_run = False
                    self.lightshowThread.join()
                except Exception:
                    pass

                if (tag_event.identifier in tags['identifier']):
                    logging.info("identifier is in tags")
                    logging.info(tags['identifier'])
                    if current_tag == None:
                        previous_tag = tag_event.identifier
                    else:
                        previous_tag = current_tag
                    current_tag = tag_event.identifier
                    # A tag has been matched
                    if ('playlist' in tags['identifier'][tag_event.identifier]):
                        playlist = tags['identifier'][tag_event.identifier]['playlist']
                        if ('shuffle' in tags['identifier'][tag_event.identifier]):
                            shuffle = True
                        else:
                            shuffle = False
                        self.playPlaylist(playlist, mp3_dir, shuffle)
                    if ('mp3' in tags['identifier'][tag_event.identifier]):
                        filename = tags['identifier'][tag_event.identifier]['mp3']
                        self.playMp3(filename, mp3_dir)
                    if ('slack' in tags['identifier'][tag_event.identifier]):
                        webhook.Requests.post(tags['slack_hook'],{'text': tags['identifier'][tag_event.identifier]['slack']})
                    if ('command' in tags['identifier'][tag_event.identifier]):
                        command = tags['identifier'][tag_event.identifier]['command']
                        logger.info('Running command %s' % command)
                        os.system(command)
                    if ('webhook' in tags['identifier'][tag_event.identifier]):
                        hook = tags['identifier'][tag_event.identifier]['webhook']
                        logger.info("calling a webhook, url: %s", hook)
                        try:
                            logger.info('oooookay')
                            response = webhook.Requests.post(hook, {})
                            logger.info(response)
                        except BaseException as e:
                            logger.info('failed calling webhook, error: %s', e)
                    if ('spotify' in tags['identifier'][tag_event.identifier]) and spotify.activated():
                        if current_tag == previous_tag:
                            self.startLightshow(spotify.resume())
                            continue
                        try:
                            position_ms = int(tags['identifier'][tag_event.identifier]['position_ms'])
                        except Exception:
                            position_ms = 0
                        self.stopMp3()
                        duration_ms = spotify.spotcast(tags['identifier'][tag_event.identifier]['spotify'],
                                                        position_ms)
                        if duration_ms > 0:
                            self.startLightshow(duration_ms)
                        else:
                            self.base.flash_pad(pad = tag_event.pad_num, on_length = 10, off_length = 10,
                                                pulse_count = 6, colour = self.RED)
                    if ('spotify' in tags['identifier'][tag_event.identifier]) and not spotify.activated():
                        current_tag = previous_tag
                else:
                    unknown_tag = nfctags.UnknownTag(tag_event.identifier)
                    # Unknown tag. Display UID.
                    logger.info('Discovered new tag: %s' % tag_event.identifier)
                    self.base.switch_pad(tag_event.pad_num, unknown_tag.get_pad_color())
