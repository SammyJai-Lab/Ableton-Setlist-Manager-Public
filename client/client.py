import argparse
import threading
import time
from flask import Flask, request, jsonify, render_template
from pythonosc.udp_client import SimpleUDPClient, OscBundle, OscMessageBuilder
from pythonosc.osc_bundle_builder import OscBundleBuilder
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer
from typing import Callable, Iterable
import datetime

app = Flask(__name__)

REMOTE_PORT = 11000
LOCAL_PORT = 11001

#--------------------------------------------------------------------------------
# An Ableton Live tick is 100ms. This constant is typically used for timeouts,
# and factors in some extra time for processing overhead.
#--------------------------------------------------------------------------------
TICK_DURATION = 0.150

class AbletonOSCClient:
    def __init__(self, hostname="127.0.0.1", port=REMOTE_PORT, client_port=LOCAL_PORT):
        """
        Create a client to connect to an Ableton OSC instance.
        Args:
            hostname: The remote host to connect to.
            port: The remote port to connect to. Defaults to 11000, the default AbletonOSC port.
            client_port: The local port to bind to. Defaults to 11001, the default AbletonOSC reply port.
        """
        dispatcher = Dispatcher()
        dispatcher.set_default_handler(self.handle_osc)
        self.server = ThreadingOSCUDPServer(("0.0.0.0", client_port), dispatcher)
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.start()
        self.address_handlers = {}
        self.client = SimpleUDPClient(hostname, port)
        self.verbose = False

    def handle_osc(self, address, *params):
        # print("Received OSC: %s %s" % (address, params))
        if address in self.address_handlers:
            self.address_handlers[address](address, params)
        if self.verbose:
            print(address, params)

    def stop(self):
        self.server.shutdown()
        self.server_thread.join()
        self.server = None

    def send_bundle(self,
                    messages: list[tuple[str, tuple]]):

        import time
        now = int(time.time())
        bundle_builder = OscBundleBuilder(now)
        for address, params in messages:
            builder = OscMessageBuilder(address=address)
            for param in params:
                builder.add_arg(param)
            msg = builder.build()
            bundle_builder.add_content(msg)
        bundle = bundle_builder.build()
        self.client.send(bundle)

    def send_message(self,
                     address: str,
                     params: Iterable = ()):
        """
        Send a message to the given OSC address on the server.

        Args:
            address (str): The OSC address to send to (e.g. /live/song/set/tempo)
            params (Iterable): Optional list of arguments to pass to the OSC message.
        """
        self.client.send_message(address, params)

    def set_handler(self,
                    address: str,
                    fn: Callable = None):
        """
        Set the handler for the specified OSC message.

        Args:
            address (str): The OSC address to listen for (e.g. /live/song/get/tempo)
            fn (Callable): The function to trigger when a message received.
                           Must accept a two arguments:
                            - str: the OSC address
                            - tuple: the OSC parameters
        """
        self.address_handlers[address] = fn

    def remove_handler(self,
                       address: str):
        """
        Remove the handler for the specified OSC message.

        Args:
            address (str): The OSC address whose handler to remove.
        """
        del self.address_handlers[address]

    def await_message(self,
                      address: str,
                      timeout: float = TICK_DURATION):
        """
        Awaits a reply from the given `address`, and optionally asserts that the function `fn`
        returns True when called with the returned OSC parameters.

        Args:
            address: OSC query (and reply) address
            fn: Optional assertion function
            timeout: Maximum number of seconds to wait for a successful reply

        Returns:
            True if the reply is received within the timeout period and the assertion succeeds,
            False otherwise

        """
        rv = None
        _event = threading.Event()

        def received_response(address, params):
            print("Received response: %s %s" % (address, str(params)))
            nonlocal rv
            nonlocal _event
            rv = params
            _event.set()

        self.set_handler(address, received_response)
        _event.wait(timeout)
        self.remove_handler(address)
        if not _event.is_set():
            raise RuntimeError("No response received to query: %s" % address)
        return rv

    def query(self,
              address: str,
              params: tuple = (),
              timeout: float = TICK_DURATION):
        rv = None
        _event = threading.Event()

        def received_response(address, params):
            nonlocal rv
            nonlocal _event
            rv = params
            _event.set()

        self.set_handler(address, received_response)
        self.send_message(address, params)
        _event.wait(timeout)
        self.remove_handler(address)
        if not _event.is_set():
            raise RuntimeError("No response received to query: %s" % address)
        return rv

@app.route('/')
def index():
    cache_buster = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    return render_template('index.html', cache_buster=cache_buster)

@app.route('/get_cue_points', methods=['GET'])
def get_cue_points():
    cue_points = ableton_client.query("/live/song/get/cue_points")
    cue_points_list = []
    for i in range(0, len(cue_points), 2):
        cue_points_list.append([cue_points[i], cue_points[i + 1]])
    sorted_cue_points = sorted(cue_points_list, key=lambda x: x[1])
    return jsonify(sorted_cue_points)

@app.route('/play_song', methods=['POST'])
def play_song():
    data = request.json
    cue_index = data['cue_index']
    cue_points = data['cue_points']
    selected_cue = cue_points[cue_index]
    ableton_client.send_message("/live/song/cue_point/jump", [selected_cue[0]])
    ableton_client.send_message("/live/song/start_playing")
    start_pos = selected_cue[1]
    stop_pos = None
    for cue in cue_points[cue_index:]:
        if cue[0].lower() == "stop":
            stop_pos = cue[1]
            break
    return jsonify({'start_pos': start_pos, 'stop_pos': stop_pos})

@app.route('/monitor_playhead', methods=['POST'])
def monitor_playhead():
    stop_pos = request.json['stop_pos']
    while True:
        current_position = ableton_client.query("/live/song/get/current_song_time")[0]
        if abs(current_position - stop_pos) < 1:
            ableton_client.send_message("/live/song/stop_playing")
            break
        time.sleep(TICK_DURATION)
    return jsonify({'status': 'stopped'})

@app.route('/stop_song', methods=['POST'])
def stop_song():
    ableton_client.send_message("/live/song/stop_playing")
    return jsonify({'status': 'stopped'})
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Client for AbletonOSC")
    parser.add_argument("--hostname", type=str, default="127.0.0.1")
    parser.add_argument("--port", type=str, default=11000)
    args = parser.parse_args()

    ableton_client = AbletonOSCClient(args.hostname, int(args.port))
    app.run(host='0.0.0.0', port=5000)