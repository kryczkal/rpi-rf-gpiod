"""
Sending and receiving 433/315Mhz signals with low-cost GPIO RF Modules on a Raspberry Pi.
"""

import logging
import time
from collections import namedtuple

import gpiod

MAX_CHANGES = 67
GPIO_CHIP = "/dev/gpiochip0"

_LOGGER = logging.getLogger(__name__)

Protocol = namedtuple(
    "Protocol",
    [
        "pulselength",
        "sync_high",
        "sync_low",
        "zero_high",
        "zero_low",
        "one_high",
        "one_low",
    ],
)
PROTOCOLS = (
    None,
    Protocol(350, 1, 31, 1, 3, 3, 1),
    Protocol(650, 1, 10, 1, 2, 2, 1),
    Protocol(100, 30, 71, 4, 11, 9, 6),
    Protocol(380, 1, 6, 1, 3, 3, 1),
    Protocol(500, 6, 14, 1, 2, 2, 1),
    Protocol(200, 1, 10, 1, 5, 1, 1),
)


class RFDevice:
    """Representation of a GPIO RF device."""

    # pylint: disable=too-many-instance-attributes,too-many-arguments
    def __init__(
        self,
        gpio_num,
        tx_proto=1,
        tx_pulselength=None,
        tx_repeat=10,
        tx_length=24,
        rx_tolerance=80,
    ):
        """Initialize the RF device."""
        self.gpio_num = gpio_num
        self.tx_proto = tx_proto
        if tx_pulselength:
            self.tx_pulselength = tx_pulselength
        else:
            self.tx_pulselength = PROTOCOLS[tx_proto].pulselength
        self.tx_repeat = tx_repeat
        self.tx_length = tx_length
        self.rx_tolerance = rx_tolerance

        self.request = None

        # internal values
        self._rx_timings = [0] * (MAX_CHANGES + 1)
        self._rx_last_timestamp = 0
        self._rx_change_count = 0
        self._rx_repeat_count = 0

        # successful RX values
        self.rx_code = None
        self.rx_code_timestamp = None
        self.rx_proto = None
        self.rx_bitlength = None
        self.rx_pulselength = None

        _LOGGER.debug("Using GPIO %d", self.gpio_num)

    def cleanup(self):
        """Release GPIO resources."""
        if self.request:
            self.request.close()
            _LOGGER.debug("GPIO resources released.")

    def enable_tx(self):
        """Enable transmitter mode."""
        if self.request:
            self.request.close()

        config = {
            self.gpio_num: gpiod.LineSettings(
                direction=gpiod.Direction.OUTPUT, output_value=gpiod.Value.INACTIVE
            )
        }
        self.request = gpiod.request_lines(
            GPIO_CHIP, consumer="rpi-rf-gpiod-tx", config=config
        )
        _LOGGER.debug("TX enabled")

    def enable_rx(self):
        """Enable receiver mode."""
        if self.request:
            self.request.close()

        config = {
            self.gpio_num: gpiod.LineSettings(
                edge_detection=gpiod.Edge.BOTH,
                bias=gpiod.Bias.PULL_DOWN,
                debounce_period_us=50,
            )
        }
        self.request = gpiod.request_lines(
            GPIO_CHIP, consumer="rpi-rf-gpiod-rx", config=config
        )
        _LOGGER.debug("RX enabled")

    def tx_code(self, code, tx_proto=None, tx_pulselength=None, tx_length=None):
        """
        Send a decimal code.
        """
        if tx_proto:
            self.tx_proto = tx_proto
        else:
            self.tx_proto = 1
        if tx_pulselength:
            self.tx_pulselength = tx_pulselength
        elif not self.tx_pulselength:
            self.tx_pulselength = PROTOCOLS[self.tx_proto].pulselength
        if tx_length:
            self.tx_length = tx_length
        elif self.tx_proto == 6:
            self.tx_length = 32
        elif code > 16777216:
            self.tx_length = 32
        else:
            self.tx_length = 24
        rawcode = format(code, "#0{}b".format(self.tx_length + 2))[2:]
        if self.tx_proto == 6:
            nexacode = ""
            for b in rawcode:
                if b == "0":
                    nexacode = nexacode + "01"
                if b == "1":
                    nexacode = nexacode + "10"
            rawcode = nexacode
            self.tx_length = 64
        _LOGGER.debug("TX code: " + str(code))
        return self.tx_bin(rawcode)

    def tx_bin(self, rawcode):
        """Send a binary code."""
        _LOGGER.debug("TX bin: " + str(rawcode))
        for _ in range(0, self.tx_repeat):
            if self.tx_proto == 6:
                if not self.tx_sync():
                    return False
            for byte in range(0, self.tx_length):
                if rawcode[byte] == "0":
                    if not self.tx_l0():
                        return False
                else:
                    if not self.tx_l1():
                        return False
            if not self.tx_sync():
                return False

        return True

    def tx_l0(self):
        """Send a '0' bit."""
        if not 0 < self.tx_proto < len(PROTOCOLS):
            _LOGGER.error("Unknown TX protocol")
            return False
        return self.tx_waveform(
            PROTOCOLS[self.tx_proto].zero_high, PROTOCOLS[self.tx_proto].zero_low
        )

    def tx_l1(self):
        """Send a '1' bit."""
        if not 0 < self.tx_proto < len(PROTOCOLS):
            _LOGGER.error("Unknown TX protocol")
            return False
        return self.tx_waveform(
            PROTOCOLS[self.tx_proto].one_high, PROTOCOLS[self.tx_proto].one_low
        )

    def tx_sync(self):
        """Send a sync."""
        if not 0 < self.tx_proto < len(PROTOCOLS):
            _LOGGER.error("Unknown TX protocol")
            return False
        return self.tx_waveform(
            PROTOCOLS[self.tx_proto].sync_high, PROTOCOLS[self.tx_proto].sync_low
        )

    def tx_waveform(self, highpulses, lowpulses):
        """Send basic waveform."""
        if not self.request:
            _LOGGER.error("TX not enabled")
            return False
        self.request.set_value(self.gpio_num, gpiod.Value.ACTIVE)
        self._sleep((highpulses * self.tx_pulselength) / 1000000)
        self.request.set_value(self.gpio_num, gpiod.Value.INACTIVE)
        self._sleep((lowpulses * self.tx_pulselength) / 1000000)
        return True

    def rx_listen(self):
        """Generator that listens for and yields received codes."""
        _LOGGER.info("Listening for codes on GPIO %d", self.gpio_num)
        self.enable_rx()
        try:
            while True:
                if self.request.wait_edge_events(sec=1):
                    events = self.request.read_edge_events()
                    for event in events:
                        self._process_rx_event(event)
                        # After processing, check if a new code was decoded
                        if self.rx_code is not None:
                            yield {
                                "code": self.rx_code,
                                "pulselength": self.rx_pulselength,
                                "protocol": self.rx_proto,
                            }
                            # Reset after yielding
                            self.rx_code = None
        finally:
            self.cleanup()

    def _process_rx_event(self, event):
        """Process a gpiod.EdgeEvent."""
        timestamp = event.timestamp_ns // 1000
        duration = timestamp - self._rx_last_timestamp

        if duration > 5000:
            if abs(duration - self._rx_timings[0]) < 200:
                self._rx_repeat_count += 1
                self._rx_change_count -= 1
                if self._rx_repeat_count == 2:
                    for pnum in range(1, len(PROTOCOLS)):
                        if self._rx_waveform(pnum, self._rx_change_count, timestamp):
                            _LOGGER.debug("RX code " + str(self.rx_code))
                            break
                    self._rx_repeat_count = 0
            self._rx_change_count = 0

        if self._rx_change_count >= MAX_CHANGES:
            self._rx_change_count = 0
            self._rx_repeat_count = 0
        self._rx_timings[self._rx_change_count] = duration
        self._rx_change_count += 1
        self._rx_last_timestamp = timestamp

    def _rx_waveform(self, pnum, change_count, timestamp):
        """Detect waveform and format code."""
        code = 0
        delay = int(self._rx_timings[0] / PROTOCOLS[pnum].sync_low)
        delay_tolerance = delay * self.rx_tolerance / 100

        for i in range(1, change_count, 2):
            if (
                abs(self._rx_timings[i] - delay * PROTOCOLS[pnum].zero_high)
                < delay_tolerance
                and abs(self._rx_timings[i + 1] - delay * PROTOCOLS[pnum].zero_low)
                < delay_tolerance
            ):
                code <<= 1
            elif (
                abs(self._rx_timings[i] - delay * PROTOCOLS[pnum].one_high)
                < delay_tolerance
                and abs(self._rx_timings[i + 1] - delay * PROTOCOLS[pnum].one_low)
                < delay_tolerance
            ):
                code <<= 1
                code |= 1
            else:
                return False

        if self._rx_change_count > 6 and code != 0:
            self.rx_code = code
            self.rx_code_timestamp = timestamp
            self.rx_bitlength = int(change_count / 2)
            self.rx_pulselength = delay
            self.rx_proto = pnum
            return True

        return False

    def _sleep(self, delay):
        end = time.perf_counter() + delay
        while time.perf_counter() < end:
            pass
