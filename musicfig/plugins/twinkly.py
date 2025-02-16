import json
import os
import time
import xled

from .core import BasePlugin
from ..lego import DimensionsTagEvent
from ..nfc_tag import NFCTag, NFCTagOperationError

class TwinklyTag(NFCTag):
    required_attributes = ["pattern"]
    DEFAULT_FPS = 30

    @classmethod
    def get_attributes_description(cls):
        return json.dumps({
            "pattern": "[Required] name of the pattern file to load, excluding the path",
            "fps": "[Optional] how many frames per second the pattern should play at (default is 30)"
        }, indent=4)
    
    def _init_attributes(self):
        super()._init_attributes()
        self.pattern = self.attributes["pattern"]
        try:
            self.fps = int(self.attributes.get("fps", TwinklyTag.DEFAULT_FPS))
        except ValueError as e:
            self.logger.warning("bad value in 'fps' attribute on '%s': [%s]; number expected", self.pattern, self.attributes.get("fps"))
            self.fps = TwinklyTag.DEFAULT_FPS
        
    def get_ms_per_frame(self):
        """
        Fetches the number of frames per second converted to the number of milliseconds per frame

        Returns:
        int-cast number of ms per frame (e.g. 33 instead of 33.333333 for fps of 30)
        """
        return int(1000 / self.fps)


class TwinklyPlugin(BasePlugin):

    TAG_CLASS = TwinklyTag

    ###############################
    # configuration, setup, initialization, registration operations
    ###############################
    def init_app(self, app):
        """
        Build Twinkly interface along with other setup from `BasePlugin.init_app`

        Raises PluginError if the config is not defined properly
        """
        super().init_app(app)

        # maybe get rid of magic constants?
        self.pattern_dir = self._get_from_config_or_fail("TWINKLY_PATTERN_DIR")
        self.ip_address = self._get_from_config_or_fail("TWINKLY_IP_ADDRESS")
        self.mac_address = self._get_from_config_or_fail("TWINKLY_MAC_ADDRESS")
        self.control_interface = xled.ControlInterface(self.ip_address, self.mac_address)
    

    ###############################
    # Operational
    ###############################
    def _start_pattern(self, twinkly_tag: TwinklyTag):
        """
        Switches the pattern on the tree to the one defined by the tag

        In Twinkly V1, this is four network operations, executed in serial (meaning
        it's slow). The operations are
        - stop device playback
        - send the pattern file contents to the device
        - update the configuration to play the pattern properly
        - begin playback again

        Obviously, a lot can go wrong, so we're doing a bit of validation all through this

        Positional arguments:
        pattern -- string representing a file on the musicfig device
        """
        self.logger.debug("Twinkly - requested pattern %s", twinkly_tag.pattern)

        pattern_file = self._get_file_path_for_pattern(twinkly_tag.pattern)
        if pattern_file is None:
            return

        # we'll need these for calculations
        try:
            num_leds = int(self._try_network_operation('get_device_info', verify_keys=["number_of_led"])["number_of_led"])
        except ValueError as e:
            self.logger.exception("bad value for number_of_led")
            raise NFCTagOperationError("bad value for number_of_led")
            
        bytes_per_frame = num_leds * 3

        # do the tree
        self._try_network_operation("set_mode", call_args=["off"])
        with open(pattern_file, 'rb') as f:
            response = self._try_network_operation("set_led_movie_full", call_args=[f])

            # also need the size of the file
            num_frames = response.data.get("frames_number")

        # calc num frames
        if num_frames is None:
            file_size = os.path.getsize(pattern_file)
            num_frames = int(file_size / bytes_per_frame)

        call_args = [twinkly_tag.get_ms_per_frame(), num_frames, num_leds]
        self._try_network_operation("set_led_movie_config", call_args=call_args)
        self._try_network_operation("set_mode", call_args=["movie"])

    
    ###############################
    # Utility
    ###############################
    def _get_file_path_for_pattern(self, pattern):
        """
        Fetches the file path in which the requested pattern _should_ exist.

        Positional arguments:
        pattern -- string name of the pattern

        Returns:
        string file path if the pattern file exists, None otherwise
        """
        pattern_file = os.path.join(self.pattern_dir, pattern)
        if not os.path.isfile(pattern_file):
            self.logger.warning("Requested pattern %s does not exist at %s", pattern, pattern_file)
            return None
        return pattern_file
    

    def _try_network_operation(self, operation, call_args=[], verify_keys=[]):
        """
        Wraps network operations in order to better handle failures along the way

        Twinkly is... particular. And can be flaky. And verbose. And has many
        operations which need to be called to accomplish one task (e.g. changing
        a pattern takes four individual network calls). Thus, it's prudent to 
        abstract out the call so we can reuse all the error handling, etc.

        Positional args:
        operation -- name of the API method we are going to execute

        Keyword args:
        call_args: string list of the arguments to be passed to the API
        verify_keys: string list of keys which must be in a successful response

        Return:
        Varies, but generally a dict which contains a property called "code" which
        references the success of the operation. Failed network operations will return
        a None response.
        """
        start = time.time()
        func = getattr(self.control_interface, operation)
        try:
            response = func(*call_args)
        except Exception as e:
            self.logger.error("failed network operation: %s", str(e))
            response = None
        
        error = None
        addl_info = {}
        if response is None:
            error = "Twinkly API call response is empty"
        elif response.get("code") != 1000:
            error = "Code returned was not 1000"
            addl_info["code"] = response.get("code")
            addl_info["response"] = response
        else:
            for k in verify_keys:
                if response.get(k) is None:
                    error = "Twinkly API call response did not contain required key"
                    addl_info["key"] = k
                    addl_info["response"] = response
        
        if error is not None:
            msg = error + "; extra information: " + ", ".join(["%s=%s" % (k, v) for k, v in addl_info.items()])
            raise NFCTagOperationError(msg)

        end = time.time()
        self.logger.info("operation %s took %s ms", operation, int((end - start) * 1000))
        return response


    ###############################
    # Event Listeners
    ###############################
    def _on_tag_added(self, tag_event: DimensionsTagEvent, nfc_tag: NFCTag):
        self._start_pattern(nfc_tag)


twinkly_plugin = TwinklyPlugin()