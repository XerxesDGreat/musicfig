#!/usr/bin/env python

from datetime import time
from . import mp3player#, spotify
#from .spotify import spotify_client
from collections import namedtuple
from flask import current_app
from musicfig import colors
from mutagen.mp3 import MP3
from musicfig.nfc_tag import NFCTag, NFCTagManager, NFCTagOperationError
from pubsub import pub


import binascii
import glob
import logging
import os
import random
import threading
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


""" Representation of a tag addition or tag removal event """
DimensionsTagEvent = namedtuple("DimensionsTagEvent", ["was_removed", "pad_num", "identifier"])


class BaseDimensions():
    """
    requires context
    """
    def __init__(self, app):
        self.logger = app.logger

    def init_usb(self):
        pass

    def send_command(self, command):
        pass

    def change_pad_color(self, pad, colour):
        pass

    def fade_pad_color(self, pad, pulse_time, pulse_count, colour):
        pass

    def flash_pad_color(self, pad, on_length, off_length, pulse_count, colour):
        pass

    def get_tag_event(self):
        raise NotImplemented()


class FakeDimensions(BaseDimensions):
    def __init__(self, app):
        super().__init__(app)
        self.tags = []

    def get_tag_event(self):
        """
        randomly returns a tag event
        """
        seed = random.randint(1, 100000)
        if seed > 1:
            return

        other_seed = random.randint(1, 2)

        m = other_seed % 2
        removed = m == 0
        tag = None
        pad = None
        if removed:
            if len(self.tags) > 0:
                tag, pad = self.tags.pop(random.randrange(len(self.tags)))
        else:
            pad = random.randint(1, 3)
            tag = ''.join(random.choice('0123456789abcdef') for n in range(14))
            self.tags.append((tag, pad))
        
        return None if tag is None else DimensionsTagEvent(removed, pad, tag)


class Dimensions(BaseDimensions):
    """
    Representation of the LEGO Dimensions USB device. This provides the interface by which
    commands are sent and NFC tag events are detected.
    """
    VENDOR_ID = 0x0e6f
    PRODUCT_ID = 0x0241
    DEFAULT_COLOR = colors.DIM

    LEFT_PAD = 2
    RIGHT_PAD = 3
    CIRCLE_PAD = 1
    ALL_PAD = 0

    def __init__(self, app=None):
        super().__init__(app)
        try:
           self.dev = self.init_usb()
        except Exception as e:
            self.logger.exception("failed initialization: %s", e)
            raise e

    def init_usb(self):
        """
        Initializes the USB connection and prepares the device to receive commands

        Raises the following exceptions:
        ValueError if the device is not found
        usb.core.USBError on USB comms-related errors
        Other various standard exceptions, depending on the case
        """
        dev = usb.core.find(idVendor=Dimensions.VENDOR_ID, idProduct=Dimensions.PRODUCT_ID)

        if dev is None:
            self.logger.error('Lego Dimensions pad not found')
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
        """
        Converts the given command into a byte stream and sends it to the USB device

        Positional Arguments:
        command -- a byte array which represents the command to send.
        """
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
            self.logger.info("exception: %s", e)
            pass

    def change_pad_color(self, pad, colour):
        """
        Changes the color of a pad on the device to the provided color

        The allowed values for pad are as follows:
        0 - all pads
        1 - left pad
        2 - right pad
        3 - circle pad

        Positional arguments:
        pad -- the pad whose color we should change
        colour -- the new color, formatted as a tuple of ints like (R, G, B)
        """
        self.send_command([0x55, 0x06, 0xc0, 0x02, pad, colour[0], 
                          colour[1], colour[2],])

    def fade_pad_color(self, pad, pulse_time, pulse_count, colour):
        """
        Crossfades the pad from the current color to the provided color

        The allowed values for pad are as follows:
        0 - all pads
        1 - left pad
        2 - right pad
        3 - circle pad

        Positional arguments:
        pad -- the pad whose color we should change
        pulse_time -- how long the color transition should be
        pulse_count -- how many times to change color; odd will
                       remain the new color, even numbers will
                       go back to the original color
        colour -- the color for transition
        """
        self.send_command([0x55, 0x08, 0xc2, 0x0f, pad, pulse_time, 
                          pulse_count, colour[0], colour[1], colour[2],])

    def flash_pad_color(self, pad, on_length, off_length, pulse_count, colour):
        """
        Flashes the pad between the current color and the provided color

        The behavior of this is not very intuitive. Using words, this operation
        will switch between the `colour` and the current color `pulse_count` times,
        with a duration which alternates between `on_length` and `off_length`. An
        example is probably easier to follow. Assume the current color is red and
        this operation is called with the following args:
        - `on_length` = 5
        - `off_length` = 10
        - `pulse_count` = 4
        - color = blue
        This would change the pad to blue for 5, then back to red for 10, back to blue for 5,
        back to red for 10, then it would stay red. Were pulse_count 5, the pad would stay blue

        The allowed values for pad are as follows:
        0 - all pads
        1 - left pad
        2 - right pad
        3 - circle pad

        Positional arguments:
        pad -- the pad whose color we should change
        on_length -- how long to switch to the new color, seemingly in 100s of milliseconds
        off_lenth -- how long to switch back to the old color, seemingly in 100s of milliseconds
        pulse_count -- how many times to change colors; odd numbers will
                       remain the new color, even numbers will revert to
                       the original color
        colour -- the new color in a tuple of ints (R, G, B)
        """
        self.send_command([0x55, 0x09, 0xc3, 0x03, pad, 
                          on_length, off_length, pulse_count, 
                          colour[0], colour[1], colour[1],])

    def get_tag_event(self):
        """
        Fetches the most recent tag add or remove event

        Returns None if no relevant event exists, or
        a DimensionsTagEvent if there is a relevant event
        """
        try:
            inwards_packet = self.dev.read(0x81, 32, timeout = 10)
        except usb.core.USBTimeoutError:
            # it seems that this error happens every time you read if there is nothing
            # to read, thus we don't need to do any messaging about it
            return
        except Exception as e:
            self.logger.exception("encountered error while reading")
            return

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
        event = DimensionsTagEvent(removed, pad_num, identifier)
        self.logger.debug("generated event %s", event)
        return event


class DimensionsLoop(threading.Thread):
    """
    Manages the application loop for working with the Dimensions base

    The main set of tasks contained within is to poll for dimensions
    tag events, map them to database records, and dispatch events to the 
    event dispatcher for later handling.
    """

    def __init__(self, group=None, target=None, name=None, args=(), kwargs=None, *, daemon=None):
        super().__init__(group=group, target=target, name=name, args=args, kwargs=kwargs, daemon=daemon)
        self.current_active_tags = set() # this may be better in the Dimensions
        self.do_loop = True

    def init_app(self, app):
        """
        Flask-stype initializer for stuff which relies on app context.

        Gets the Dimension threaded loop ready to run within an application context.

        Positional arguments:
        app -- an instance of the Flask app, or at least its proxy
        """
        self.app = app
        self.logger = app.logger
        self.dimensions = FakeDimensions(app) if app.config.get("USE_MOCK_PAD") else Dimensions(app)
        with app.app_context():
            # @todo make this configurable somehow
            self.nfc_tag_manager = NFCTagManager.get_instance() # maybe turn this into an init_app() as well

        self.logger.info("in init id: %s", id(self.dimensions))
        self._init_event_handlers()
    
    def _init_event_handlers(self):
        """ Sets up the event handlers """
        pub.subscribe(self.on_tag_added_error, "handler_response.add.error")
        pub.subscribe(self.on_tag_added_success, "handler_response.add.success")
        pub.subscribe(self.on_tag_removed_success, "handler_response.remove.success")
    
    def stop_loop(self):
        """ Sets a flag to stop the loop. Note that the loop will stop after the current iteration"""
        self.do_loop = False

    def run(self):
        """
        Main loop of the program

        Responsible for fetching events from the pad and handling them accordingly
        """
        self.dimensions.change_pad_color(Dimensions.ALL_PAD, self.get_idle_color())
        with self.app.app_context():
            while self.do_loop:
                if random.randint(1, 10000) == 0:
                    self.logger.info("loop")
                
                tag_event = self.dimensions.get_tag_event()
                if tag_event is None:
                    continue

                try:
                    nfc_tag = self.nfc_tag_manager.get_nfc_tag_by_id(tag_event.identifier)
                    self.update_active_tags(tag_event, nfc_tag)
                    self.publish_tag_event(tag_event, nfc_tag)
                except Exception as e:
                    self.error_flash(tag_event.pad_num)
    
    def publish_tag_event(self, tag_event: DimensionsTagEvent, nfc_tag: NFCTag):
        """
        Sends a tag added/removed event to be handled by the appropriate listener (if any)

        Add event listeners using plugins in the plugin module
        
        Positional arguments:
        tag_event -- DimensionsTagEvent containing details about the event
        nfc_tag -- the tag which triggered the event
        """
        topic = "tag.removed" if tag_event.was_removed else "tag.added"
        pub.sendMessage(topic, tag_event=tag_event, nfc_tag=nfc_tag)

    def update_active_tags(self, tag_event: DimensionsTagEvent, nfc_tag: NFCTag):
        """
        Updates the tag which is currently active

        Positional arguments:
        tag_event -- DimensionsTagEvent containing details about the event
        nfc_tag -- the tag which triggered the event
        """
        if tag_event.was_removed:
            self.current_active_tags.discard(nfc_tag) # discard doesn't raise an error if the item isn't in the set
        else:
            self.current_active_tags.add(nfc_tag)

    def error_flash(self, pad_num):
        """
        Flashes the indicated pad with the error color

        Positional arguments:
        pad_num -- index of the pad to flash
        """
        self.dimensions.flash_pad_color(pad=pad_num, on_length=8, off_length=8, pulse_count=4, colour=self.get_error_color())

    ###############################
    # Event handlers
    ###############################
    def on_tag_added_error(self, tag_event: DimensionsTagEvent):
        """
        Handler for when processing a tag addition emits an error event

        Positional arguments:
        tag_event -- DimensionsTagEvent containing details about the event
        """
        self.logger.debug("tag response event handled: %s", tag_event)
        self.error_flash(tag_event.pad_num)
    
    def on_tag_added_success(self, tag_event: DimensionsTagEvent, color=None):
        """
        Handler for when processing a tag addition emits a success event

        Positional arguments:
        tag_event -- DimensionsTagEvent containing details about the event
        color -- optional int tuple representing which color the pad should become (R, G, B)
        """
        color = color if color is not None else self.get_default_active_color()
        self.dimensions.fade_pad_color(pad=tag_event.pad_num, pulse_time=10,
                                       pulse_count=1, colour=color)
        self.logger.debug("tag response event handled: %s, color: %s", tag_event, color)
    
    def on_tag_removed_success(self, tag_event: DimensionsTagEvent):
        """
        Handler for when processing a tag removal emits a success event

        Positional arguments:
        tag_event -- DimensionsTagEvent containing details about the event
        """
        self.dimensions.fade_pad_color(pad=tag_event.pad_num, pulse_time=10,
                                       pulse_count=1, colour=self.get_idle_color())
        self.logger.debug("tag response event handled: %s", tag_event)

    ###############################
    # Color handling
    ###############################
    def get_idle_color(self):
        return self.app.config.get("DEFAULT_IDLE_COLOR", colors.DIM)
    
    def get_error_color(self):
        return self.app.config.get("DEFAULT_ERROR_COLOR", colors.RED)
    
    def get_default_active_color(self):
        return self.app.config.get("DEFAULT_ACTIVE_COLOR", colors.BLUE)
    
    def get_thinking_color(self):
        return self.app.config.get("DEFAULT_THINKING_COLOR", colors.PURPLE)
    



# class Base():
#     #perhaps initialize this in such a way that the application gives up
#     def __init__(self):
#         self._init_spotify()
#         self.base = self.startLego()

#     def _init_spotify(self):
#         cur_obj = current_app._get_current_object()
#         config = cur_obj.config

#         # spotify_client_config = SpotifyClientConfig(config.get("CLIENT_ID"),
#         #     config.get("CLIENT_SECRET"), config.get("REDIRECT_URI"))

#         # self.spotify_client = SpotifyClient.get_client(client_config=spotify_client_config)

#     # def randomLightshow(self,duration = 60):
#     #     logger.info("Lightshow started for %s seconds." % duration)
#     #     self.lightshowThread = threading.currentThread()
#     #     t = time.perf_counter()
#     #     while getattr(self.lightshowThread, "do_run", True) and (time.perf_counter() - t) < duration:
#     #         pad = random.randint(0,2)
#     #         self.colour = random.randint(0,len(self.COLOURS)-1)
#     #         self.base.change_pad_color(pad,eval(self.COLOURS[self.colour]))
#     #         time.sleep(round(random.uniform(0,0.5), 1))
#     #     self.base.change_pad_color(0,self.OFF)

#     # def startLightshow(self,duration_ms):
#     #     if switch_lights:
#     #         self.lightshowThread = threading.Thread(target=self.randomLightshow,
#     #             args=([(duration_ms / 1000)]))
#     #         self.lightshowThread.daemon = True
#     #         self.lightshowThread.start()


#     def startLego(self):
#         global current_tag
#         global previous_tag
#         global mp3state
#         #global switch_lights
#         current_tag = None
#         previous_tag = None
#         mp3state = None
#         nfc = NFCTagManager.get_instance()
#         try:
#             self.base = Dimensions()
#         except Exception as e:
#             logger.exception("Unable to initialize Dimensions; aborting")
#             return False
            
#         logger.info("Lego Dimensions base activated.")
#         self.initMp3()
#         #switch_lights = current_app.config["RUN_LIGHT_SHOW_DEFAULT"]
#         #logger.info('Lightshow is %s' % switch_lights) #("disabled", "enabled")[switch_lights])
#         self.base.change_pad_color(0, colors.DIM)
#         # if switch_lights:
#         #     self.base.change_pad_color(0,self.GREEN)
#         # else:
#         #     self.base.change_pad_color(0,self.OFF)

#         i = 0
#         while True:
#             #time.sleep(1)
#             i = i + 1
#             if i == 10000:
#                 logging.info("loop")
#                 i = 0
#             tag_event = self.base.get_tag_event()
#             if not tag_event:
#                 continue

#             # status = tag.split(':')[0]
#             # pad = int(tag.split(':')[1])
#             # identifier = tag.split(':')[2]
#             logging.info(tag_event)

#             if tag_event.was_removed:
#                 self.base.change_pad_color(pad=tag_event.pad_num, colour=colors.DIM)
#                 if tag_event.identifier == current_tag:
#                     # try:
#                     #     self.lightshowThread.do_run = False
#                     #     self.lightshowThread.join()
#                     # except Exception:
#                     #     pass
#                     self.pauseMp3()
#                     if spotify_client.is_activated():
#                         spotify_client.pause()
#                     # if self.spotify_client.is_activated():
#                     #     self.spotify_client.pause()
#                 elif isinstance(current_tag, SpotifyTag) and tag_event.identifier == current_tag.identifier:
#                     self.pauseMp3()
#                     if spotify_client.is_activated():
#                         spotify_client.pause()
#                     # if self.spotify_client.is_activated():
#                     #     self.spotify_client.pause()
#             else:
#                 self.base.change_pad_color(pad=tag_event.pad_num, colour=colors.BLUE)

#                 mp3_dir = current_app.config["MP3_DIR"]
#                 ##logger.debug(mp3_dir)

#                 # Stop any current songs and light shows
#                 # try:
#                 #     self.lightshowThread.do_run = False
#                 #     self.lightshowThread.join()
#                 # except Exception:
#                 #     pass

#                 # nfc_tag could be a dict or an NFCTag object
#                 nfc_tag = nfc.get_nfc_tag_by_id(tag_event.identifier)
#                 logging.info(nfc_tag)

#                 previous_tag = current_tag
#                 current_tag = nfc_tag.identifier

#                 if nfc_tag.should_use_class_based_execution():
#                     logging.info("doing new")
#                     try:
#                         nfc_tag.on_add()
#                     except NFCTagOperationError as e:
#                         logger.exception(e)
#                         self.base.flash_pad_color(pad=tag_event.pad_num, on_length=8, off_length=8, pulse_count=4, colour=colors.RED)
                
#                 else:
#                     if isinstance(nfc_tag, SpotifyTag):
#                         logger.info("spotify tag")
#                         if spotify_client.is_activated():
#                         #if self.spotify_client.is_activated():
#                             logger.info("activated")
#                             if current_tag == previous_tag:
#                                 spotify_client.resume()
#                                 #self.spotify_client.resume()
#                                 #self.startLightshow(self.spotify_client.resume())
#                                 continue
#                             self.stopMp3()
#                             duration_ms = spotify_client.spotcast(nfc_tag.spotify_uri, nfc_tag.start_position_ms)
#                             #duration_ms = self.spotify_client.spotcast(nfc_tag.spotify_uri, nfc_tag.start_position_ms)
#                             # if duration_ms > 0:
#                             #     self.startLightshow(duration_ms)
#                             #else:
#                             # self.base.flash_pad_color(pad=tag_event.pad_num, on_length=10,
#                             #     off_length=10, pulse_count=2, colour=self.RED)
#                         else: 
#                             logger.info("not activated")
#                             current_tag = previous_tag

#                             #https://open.spotify.com/playlist/6VdvufagCnB6BS52MxwPRw?si=9718899179eb413e
                    
#                     else:
                    
#                         nfc_tag = nfc_tag.definition

#                         logging.info("doing old: %s", nfc_tag)
#                         # if current_tag == None:
#                         #     previous_tag = tag_event.identifier
#                         # else:
#                         # A tag has been matched
#                         if 'playlist' in nfc_tag:
#                             playlist = nfc_tag['playlist']
#                             if 'shuffle' in nfc_tag:
#                                 shuffle = True
#                             else:
#                                 shuffle = False
#                             self.playPlaylist(playlist, mp3_dir, shuffle)
#                         if 'mp3' in nfc_tag:
#                             filename = nfc_tag['mp3']
#                             self.playMp3(filename, mp3_dir)
#                         if 'command' in nfc_tag:
#                             command = nfc_tag['command']
#                             logger.info('Running command %s' % command)
#                             os.system(command)
                    
