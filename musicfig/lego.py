from collections import namedtuple
from musicfig import colors

import binascii
import logging
import random
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
                          colour[0], colour[1], colour[2],])

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
        except usb.core.USBError as e:
            # this one we _do_ want to raise as it will help us with handling shutdown
            raise e
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
    
