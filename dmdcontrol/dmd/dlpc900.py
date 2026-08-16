"""
DLPC900 USB HID driver — pycrafter6500 protocol.

Packet layout:
  Byte 0      flag   0x40 = write+ACK, 0xC0 = read+reply
  Byte 1      seq    auto-incrementing counter
  Bytes 2-3   plen   2 (cmd bytes) + len(data), little-endian
  Byte 4      cmd LSB
  Byte 5      cmd MSB
  Bytes 6+    data payload
"""

from __future__ import annotations

import struct
import time
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING
import usb.core
import usb.util
from .helper import select_pyusb_device
from dmdcontrol.utils import CONFIG

if TYPE_CHECKING:
    from dmdcontrol.runtime import LutEntry

@dataclass
class DMD:
    name: str
    usb_bus: int
    usb_port: tuple[int, ...]
    xrandr_output: str
    width: int
    height: int
    offset: tuple[int, int]
    target_hz: int
    hid_intf: int | None = None
    dev: usb.core.Device | None = None
    

def load_from_config() -> list[DMD]:
    """
    Load DMDs from dictionary config.
    
    **Required Keys:**
    - `name`: The name of the DMD device.
        - `usb_bus`, `usb_port`: physical usb location
        - `xrandr_output`: The xrandr output name for the DMD device.
        - `width`: The width of the DMD device.
        - `height`: The height of the DMD device.
        - `offset`: The offset of the DMD device.
        - `target_hz`: The target refresh rate in Hz.

    Raises:
        RuntimeError: Raises if any required key is missing in the config.

    Returns:
        list[DMD]: A list of loaded DMD objects.
    """
    dmds = []
    # Check for required keys
    for name in ['A', 'B']:
        try:
            dmds.append(
                DMD(
                    name=name,
                    usb_bus=int(CONFIG['DMD'][name]['usb_bus']),
                    usb_port=tuple(port) if isinstance(port := CONFIG['DMD'][name]['usb_port'], list) else (int(port),),
                    xrandr_output=CONFIG['DMD'][name]['xrandr_output'],
                    width=int(CONFIG['DMD']['width']),
                    height=int(CONFIG['DMD']['height']),
                    offset=tuple(CONFIG['DMD']['offset']),
                    target_hz=int(CONFIG['DMD']['target_hz'])
                )
            )
        except KeyError as e:
            raise RuntimeError(f"Missing required key in config for DMD '{name}': {e}")

    return dmds


class DLPC900:
    """
    Class for controlling DMDs.
    """
    def __init__(self, dmd: DMD):
        """
        Initializes teh DLPC900 class, which controls the DMDs. This selects and opens the DMD USB device that corresponds to the configuration passed in.

        Args:
            dmd (DMD): The DMD object to be opened and controlled.
        """
        # Set up logging
        self.logger = logging.getLogger('DLPC900')
        
        # Set the DMD
        self.dmd = dmd
        
        # Open the USB device and claim the HID interface
        self.open()
        
        # Initialize sequence number for command packets
        self._seq: int = 0
        
    def open(self):
        """
        Opens the DMD USB device and claims the HID interface.

        Raises:
            RuntimeError: Raises when there's no HID interface found.
        """
        # Select the USB device based on the provided DMD configuration
        self.dmd.dev = select_pyusb_device(self.dmd.usb_bus, self.dmd.usb_port)
        
        # Grab current configuration
        cfg = self.dmd.dev.get_active_configuration()

        # Detach kernel driver for all interfaces
        for intf in range(len(cfg.interfaces())):
            if self.dmd.dev.is_kernel_driver_active(intf):
                self.dmd.dev.detach_kernel_driver(intf)

        # Sets to the default configuration... probably not necessary?
        self.dmd.dev.set_configuration()

        # Dynamic HID interface enum, DLPC900 is composite USB.
        # Linux frequently puts HID on intf 1; Windows on intf 0. Hard-coded 0
        # caused silent endpoint mismatch on Linux. Find first intf with class=3.
        # ^ both interfaces are 0x03... This is picking the first one, which is intf 0...
        # Grab interface number of first HID interface (bInterfaceClass=0x03) 
        hid_intf = None
        for intf in cfg:
            if intf.bInterfaceClass == 0x03:
                hid_intf = intf.bInterfaceNumber
                break
        if hid_intf is None:
            self.logger.error('No HID interface found on the device.')
            raise RuntimeError('No HID interface found on the device.')
        self.dmd.hid_intf = hid_intf
        
        # Claim the HID interface
        self.logger.info('Claiming HID interface %d', hid_intf)
        usb.util.claim_interface(self.dmd.dev, hid_intf)
        self.logger.debug('HID interface %d claimed', hid_intf)

    def close(self):
        """
        Closes the DMD USB device.
        """
        if self.dmd.dev is None:
            self.logger.warning('DLPC900 device is already closed or was never opened.')
            return
        
        # Release the HID interface
        self.logger.info('Releasing HID interface %d', self.dmd.hid_intf)
        usb.util.release_interface(self.dmd.dev, self.dmd.hid_intf)
        
        # Dispose of USB resources
        self.logger.info('Disposing of USB resources')
        usb.util.dispose_resources(self.dmd.dev)
        
        # Remove dev
        self.dmd.dev = None

    def _seq_next(self) -> int:
        """
        Gets the next sequence number for command packets.

        Returns:
            int: The next sequence number, which is an 8-bit value that wraps around after 255.
        """
        v = self._seq & 0xFF
        self._seq = (self._seq + 1) & 0xFF
        return v

    def _command(self, read: bool, cmd_id: int, data: bytes = b""):
        """
        Send a command and drain the response.
        
        Args:
            read (bool): Whether the command is to read (True) or write (False).
            cmd_id (int): The command ID.
            data (bytes): The data to send with the command, if any.
            
        Returns:
            bytes: The response data, if any.
        """
        # Build full packet: header + data, then split into 64-byte frames.
        flag = 0xC0 if read else 0x40
        seq = self._seq_next()
        plen = 2 + len(data)

        buf = bytearray(
            [
                flag,
                seq,
                plen & 0xFF,
                (plen >> 8) & 0xFF,
                cmd_id & 0xFF,  # LSB → byte 4
                (cmd_id >> 8) & 0xFF,  # MSB → byte 5
            ])
        buf.extend(data)
        
        # Send the packet in 64-byte chunks, padding with zeros if necessary. Retry on USBError.
        for off in range(0, max(len(buf), 1), 64):
            chunk = bytes(buf[off:off + 64]).ljust(64, b"\x00")
            try:
                self.dmd.dev.write(0x01, chunk, timeout=2000)
            except usb.core.USBError:
                self.logger.warning('USB write failed, retrying...')
                time.sleep(0.1)
                self.dmd.dev.write(0x01, chunk)

        # Read the response, trying up to 6 times.
        resp = None
        last_resp = None
        for _ in range(6):
            try:
                r = bytes(self.dmd.dev.read(0x81, 64, timeout=2000))
            except Exception:
                self.logger.warning('USB read failed, skipping...')
                break
            base = 1 if (len(r) >= 2 and r[0] == 0x00) else 0
            if len(r) > base + 1:
                stripped = bytes(r[base:])
                last_resp = stripped
                if stripped[1] == seq:
                    resp = stripped
                    break

        # NACK detection.
        if resp is not None and (resp[0] & 0x20):
            self.logger.warning('[NACK] Firmware rejected cmd 0x%04X (flags=0x%02X). Check command validity for current display mode.', cmd_id, resp[0])
        return resp if resp is not None else last_resp

    def _write(self, cmd_id: int, data: bytes = b""):
        """
        Write data to DMD device over USB.

        Args:
            cmd_id (int): The command ID.
            data (bytes, optional): The data to send with the command. Defaults to `b""`.
        """
        self._command(False, cmd_id, data)

    def _read(self, cmd_id: int) -> bytes | None:
        """
        Read data from the DMD device over USB.

        Args:
            cmd_id (int): The command ID.

        Returns:
            bytes | None: The response data, if any.
        """
        return self._command(True, cmd_id, b"")

    def _payload(self, resp: bytes | None, min_len: int = 1) -> bytes | None:
        """
        Extract data payload from a read response.

        Handles two firmware layouts:
          [flag, seq, lenL, lenH, cmdL, cmdH, data...]  (with command echo)
          [flag, seq, lenL, lenH, data...]               (no command echo)
          
        Args:
            resp (bytes | None): The response data from the DMD device.
            min_len (int, optional): Minimum length of the payload to consider valid. Defaults to 1.
            
        Returns:
            bytes | None: The extracted payload data, or `None` if the response was None or had a length less than 4.
        """
        if resp is None or len(resp) < 4:
            return None
        plen = resp[2] | (resp[3] << 8)
        if plen == 0:
            return b""
        if len(resp) >= 7 and plen >= 2:
            d = resp[6:6 + (plen - 2)]
            if len(d) >= min_len:
                return d
        d = resp[4:4 + plen]
        return d if len(d) >= min_len else None

    # --- status / diagnostic ---
    def get_display_mode(self) -> tuple[int | None, None]:
        """
        Gets the current display mode of the DMD.

        Returns:
            tuple[int | None, None]: A tuple containing the display mode (or `None` if not available) and `None`.
        """
        resp = self._read(0x1A1B)
        p = self._payload(resp)
        return (p[0], None) if p else (None, None)

    def get_hardware_status(self) -> int | None:
        """
        Gets the current hardware status of the DMD.

        Returns:
            int | None: The hardware mode or None.
        """
        resp = self._read(0x1A0A)
        p = self._payload(resp)
        return p[0] if p else None

    def get_last_error(self) -> int | None:
        """
        Get the last error from the DMD.

        Returns:
            int | None: The last error code or None if there's no error.
        """
        resp = self._read(0x0100)
        p = self._payload(resp)
        return p[0] if p else None

    def get_error_description(self) -> str | None:
        """
        Get the error description from the DMD error response.

        Returns:
            str | None: Error description or None if there's no error.
        """
        resp = self._read(0x0101)
        p = self._payload(resp)
        if not p:
            return None
        try:
            desc = bytes(p).split(b"\x00", 1)[0].decode('ascii', errors='replace')
            self.logger.debug('Error description: %s', desc)
            return desc
        except Exception:
            self.logger.exception('Failed to decode error description.')
            self.logger.debug('Raw error description bytes: %s', p)
            return repr(bytes(p))

    def get_main_status(self) -> dict[str, bool | str] | None:
        """
        Get the status of the DMD.

        **Dictionary keys:**
        - `dmd_parked`: True if the DMD is parked, False otherwise.
        - `sequencer_running`: True if the sequencer is running, False otherwise.
        - `video_frozen`: True if the video is frozen, False otherwise.
        - `external_source_locked`: True if the external source is locked, False otherwise.
        - `port1_syncs_valid`: True if port 1 syncs are valid, False otherwise.
        - `port2_syncs_valid`: True if port 2 syncs are valid, False otherwise.
        - `raw`: The raw status byte in hexadecimal format.
        
        Returns:
            dict[str, bool | str] | None: Status dictionary or None if there's no response.
        """
        resp = self._read(0x1A0C)
        p = self._payload(resp)
        if p:
            v = p[0]
            return {
                "dmd_parked": bool(v & 0x01),
                "sequencer_running": bool(v & 0x02),
                "video_frozen": bool(v & 0x04),
                "external_source_locked": bool(v & 0x08),
                "port1_syncs_valid": bool(v & 0x10),
                "port2_syncs_valid": bool(v & 0x20),
                "raw": hex(v),
            }
        return None

    def get_firmware_version(self) -> dict[str, dict[str, int] | str] | None:
        """
        0x0205: 16-byte response. Returns dict with app/api/swcfg/seqcfg versions.
        
        **Dictionary keys:**
        - `app`: Dictionary containing the application firmware version.
        - `api`: Dictionary containing the API firmware version.
        - `sw_cfg`: Dictionary containing the software configuration version.
        - `seq_cfg`: Dictionary containing the sequencer configuration version.
        
        Returns:
            dict[str, dict[str, int] | str] | None: A dictionary containing the firmware version or None if there's no response.
        """
        resp = self._read(0x0205)
        p = self._payload(resp, min_len=16)
        if not p or len(p) < 16:
            self.logger.warning('Firmware version response too short or missing.')
            return None

        # I cannot describe how deeply I loath nested functions... However, I suppose in this one instance it makes sense...
        def _ver(buf):
            return {
                "major": buf[3],
                "minor": buf[2],
                "patch": buf[0] | (buf[1] << 8),
                "str": f"{buf[3]}.{buf[2]}.{buf[0] | (buf[1] << 8)}",
            }

        return {
            "app": _ver(p[0:4]),
            "api": _ver(p[4:8]),
            "sw_cfg": _ver(p[8:12]),
            "seq_cfg": _ver(p[12:16]),
        }

    def get_channel_swap(self) -> dict[str, int | str] | None:
        """
        0x1A37: Returns channel-swap config byte.

        Bit 0 = port (0=P1, 1=P2). Bits 3:1 = swap mode:
          0=ABC, 1=CAB, 2=BCA, 3=ACB, 4=BAC, 5=CBA (DLPU018J Table 2-50).
        Default reset = 0x8 (port=0, swap=4 = BAC = A/B swapped).
        
        **Dictionary keys:**
        - `raw`: The raw channel swap value in hexadecimal format.
        - `port`: The port number as a string (e.g., "P1" or "P2").
        - `swap_code`: The swap code as an integer.
        - `swap_label`: The swap label as a string (e.g., "ABC", "CAB", etc.) or "Unknown" if the swap code is not recognized.
        
        Returns:
            dict[str, int | str] | None: A dictionary containing the channel swap configuration or None if there's no response.
        """
        resp = self._read(0x1A37)
        p = self._payload(resp)
        if not p:
            self.logger.warning('Channel swap response missing or invalid.')
            return None
        v = p[0]
        port = v & 0x01
        swap = (v >> 1) & 0x07
        labels = {0: "ABC", 1: "CAB", 2: "BCA", 3: "ACB", 4: "BAC", 5: "CBA"}
        return {
            "raw": hex(v),
            "port": f"P{port + 1}",
            "swap_code": swap,
            "swap_label": labels.get(swap,
                                     f"Unknown({swap})"),
        }

    def get_display_dimensions(self) -> dict[str, int] | None:
        """
        Gets the display dimensions of the DMD.
        
        **Dictionary keys:**
        - `total_pixels_per_line`: Total number of pixels per line.
        - `total_lines_per_frame`: Total number of lines per frame.
        - `active_pixels_per_line`: Number of active pixels per line.
        - `active_lines_per_frame`: Number of active lines per frame.
        - `first_active_pixel`: The first active pixel.
        - `first_active_line`: The first active line.
        - `bottom_field_first_line`: The first line of the bottom field.
        - `pixel_clock_khz`: The pixel clock in kHz.

        Returns:
            dict[str, int] | None: Dictionary containing display information or `None` if there's no response.
        """
        resp = self._read(0x1A3C)
        p = self._payload(resp, min_len=18)
        if p and len(p) >= 18:
            return {
                "total_pixels_per_line": struct.unpack_from("<H",
                                                            p,
                                                            0)[0],
                "total_lines_per_frame": struct.unpack_from("<H",
                                                            p,
                                                            2)[0],
                "active_pixels_per_line": struct.unpack_from("<H",
                                                             p,
                                                             4)[0],
                "active_lines_per_frame": struct.unpack_from("<H",
                                                             p,
                                                             6)[0],
                "first_active_pixel": struct.unpack_from("<H",
                                                         p,
                                                         8)[0],
                "first_active_line": struct.unpack_from("<H",
                                                        p,
                                                        10)[0],
                "bottom_field_first_line": struct.unpack_from("<H",
                                                              p,
                                                              12)[0],
                "pixel_clock_khz": struct.unpack_from("<I",
                                                      p,
                                                      14)[0],
            }
            
        self.logger.warning('Display dimensions response missing or invalid.')
        return None

    def get_port_config(self) -> dict[str, str] | None:
        """
        Gets the port configuration of the DMD.
        
        **Dictionary keys:**
        - `pixel_mode`: The pixel mode as a string. Possible values:
            - "Single Pixel Port 1"
            - "Single Pixel Port 2"
            - "Dual Pixel P1-P2"
            - "Dual Pixel P2-P1"
        - `pixel_clock`: The pixel clock as a string (e.g., "Clock 1", "Clock 2", etc.).
        - `data_enable`: The data enable as a string (e.g., "DE 1", "DE 2", etc.).
        - `sync_select`: The sync select as a string (e.g., "P1 VSync/HSync", "P2 VSync/HSync", etc.).
        - `raw`: The raw port config value in hexadecimal format.

        Returns:
            dict[str, str] | None: Dictionary containing the port config or `None` if there's no response.
        """
        resp = self._read(0x1A03)
        p = self._payload(resp)
        if p:
            v = p[0]
            modes = {
                0: "Single Pixel Port 1",
                1: "Single Pixel Port 2",
                2: "Dual Pixel P1-P2",
                3: "Dual Pixel P2-P1"}
            return {
                "pixel_mode": modes.get(v & 0x03,
                                        f"Unknown({v & 0x03})"),
                "pixel_clock": f"Clock {((v >> 2) & 0x03) + 1}",
                "data_enable": f"DE {((v >> 4) & 0x01) + 1}",
                "sync_select": f"P{((v >> 5) & 0x01) + 1} VSync/HSync",
                "raw": hex(v),
            }
            
        self.logger.warning('Port config response missing or invalid.')
        return None

    def get_trigger_out_1(self) -> dict[str, int | str]:
        """
        Gets the information for Trigger Out 1 on the DMD.
        
        **Dictionary keys:**
        - `polarity`: The polarity of the trigger output. Possible values:
            - "Inverted"
            - "Non-inverted"
        - `rising_delay_us`: The rising delay in microseconds.
        - `falling_delay_us`: The falling delay in microseconds.
        - `raw`: The raw trigger output value in hexadecimal format.

        Returns:
            dict[str, int | str]: Dictionary containing the trigger config.
        """
        resp = self._read(0x1A1D)
        p = self._payload(resp, min_len=5)
        if p and len(p) >= 5:
            return {
                "polarity": "Inverted" if p[0] & 0x01 else "Non-inverted",
                "rising_delay_us": struct.unpack_from("<h",
                                                      p,
                                                      1)[0],
                "falling_delay_us": struct.unpack_from("<h",
                                                       p,
                                                       3)[0],
                "raw": p.hex(),
            }
        
        self.logger.warning('Trigger Out 1 response missing or invalid.')
        return {"raw": p.hex() if p else "NO_RESPONSE"}

    def get_trigger_out_2(self) -> dict[str, int | str]:
        """
        Gets the information for Trigger Out 2 on the DMD.

        **Dictionary keys:**
        - `polarity`: The polarity of the trigger output. Possible values:
            - "Inverted"
            - "Non-inverted"
        - `rising_delay_us`: The rising delay in microseconds.
        - `falling_delay_us`: The falling delay in microseconds.
        - `raw`: The raw trigger output value in hexadecimal format.

        Returns:
            dict[str, int | str]: Dictionary containing the trigger config.
        """
        resp = self._read(0x1A1E)
        p = self._payload(resp, min_len=5)
        if p and len(p) >= 5:
            return {
                "polarity": "Inverted" if p[0] & 0x01 else "Non-inverted",
                "rising_delay_us": struct.unpack_from("<h",
                                                      p,
                                                      1)[0],
                "falling_delay_us": struct.unpack_from("<h",
                                                       p,
                                                       3)[0],
                "raw": p.hex(),
            }
            
        self.logger.warning('Trigger Out 2 response missing or invalid.')
        return {"raw": p.hex() if p else "NO_RESPONSE"}

    # --- mode / source ---
    def set_display_mode(self, mode: int):
        """
        Sets the display mode of the DMD.

        Args:
            mode (int): Display mode.
        """
        self._write(0x1A1B, struct.pack("<B", mode))

    def set_input_source(self, source: int=0, bit_depth_sel: int=1):
        """
        Sets the input source of the DMD.

        Args:
            source (int, optional): Source. Defaults to 0.
            bit_depth_sel (int, optional): Bit depth selection. Defaults to 1.
        """
        val = (source & 0x07) | ((bit_depth_sel & 0x03) << 3)
        self._write(0x1A00, struct.pack("<B", val))

    def set_data_channel_swap(self, port: int=0, swap: int=4):
        """
        0x1A37: Set input channel swap. swap=4 is ABC->BAC for the 6500/9000 EVM.
        
        Args:
            port (int, optional): Port number. Defaults to 0.
            swap (int, optional): Swap mode. Defaults to 4.
        """
        val = (port & 0x01) | ((swap & 0x07) << 1)
        self._write(0x1A37, struct.pack("<B", val))

    def set_port_config(self, pixel_mode: int=2, pixel_clock: int=0, data_enable: int=0, sync_select: int=0):
        """
        Sets the port configuration for the DMD.

        Args:
            pixel_mode (int, optional): Pixel mode. Defaults to 2.
            pixel_clock (int, optional): Pixel clock. Defaults to 0.
            data_enable (int, optional): Data enable. Defaults to 0.
            sync_select (int, optional): Sync select. Defaults to 0.
        """
        val = (
            (pixel_mode & 0x03)
            | ((pixel_clock & 0x03) << 2)
            | ((data_enable & 0x01) << 4)
            | ((sync_select & 0x01) << 5))
        self._write(0x1A03, struct.pack("<B", val))

    def toggle_dual_pixel_mode(self, enable: bool):
        """
        Whether or not to enable dual pixel mode.

        Args:
            enable (bool): Whether or not to enable dual pixel mode.
        """
        self.set_port_config(
            pixel_mode=(2 if enable else 0),
            pixel_clock=0,
            data_enable=0,
            sync_select=0)

    def set_input_display_resolution(
            self,
            in_x: int,
            in_y: int,
            in_w: int,
            in_h: int,
            out_x: int | None=None,
            out_y: int | None=None,
            out_w: int | None=None,
            out_h: int | None=None):
        """
        Sets the display resolution. If output resolution is not specified, it will be set to match the input resolution.

        Args:
            in_x (int): Starting x-coordinate of the input resolution.
            in_y (int): Starting y-coordinate of the input resolution.
            in_w (int): Width of the input resolution.
            in_h (int): Height of the input resolution.
            out_x (int | None, optional): Starting x-coordinate of the output resolution. Defaults to None.
            out_y (int | None, optional): Starting y-coordinate of the output resolution. Defaults to None.
            out_w (int | None, optional): Width of the output resolution. Defaults to None.
            out_h (int | None, optional): Height of the output resolution. Defaults to None.
        """
        out_x = in_x if out_x is None else out_x
        out_y = in_y if out_y is None else out_y
        out_w = in_w if out_w is None else out_w
        out_h = in_h if out_h is None else out_h
        self._write(
            0x1000,
            struct.pack("<HHHHHHHH",
                        in_x,
                        in_y,
                        in_w,
                        in_h,
                        out_x,
                        out_y,
                        out_w,
                        out_h
                        ))

    # ---- LEDs ---
    def set_led_enables(self, r: bool=True, g: bool=True, b: bool=True, sequencer: bool=True):
        """
        Whether or not the LEDs are on (True) or off (False).

        Args:
            r (bool, optional): Red LED. Defaults to True.
            g (bool, optional): Green LED. Defaults to True.
            b (bool, optional): Blue LED. Defaults to True.
            sequencer (bool, optional): Sequencer LED. Defaults to True.
        """
        val = (1 if r else 0) | ((1 if g else 0) << 1) | ((1 if b else 0) << 2)
        if sequencer:
            val |= 0x08
        self._write(0x1A07, struct.pack("<B", val))

    def set_led_current(self, r: int=255, g: int=255, b: int=255):
        """
        Sets the LED current.

        Args:
            r (int, optional): Red LED. Defaults to 255.
            g (int, optional): Green LED. Defaults to 255.
            b (int, optional): Blue LED. Defaults to 255.
        """
        self._write(0x0B01, struct.pack("<BBB", r, g, b))

    # ---- DMD park ---
    def set_dmd_park(self, park: bool):
        """
        Whether or not to park the DMD.

        Args:
            park (bool): Whether or not to park the DMD.
        """
        self._write(0x0609, struct.pack("<B", 1 if park else 0))

    def apply_block_lock_workaround(self):
        """
        DLPT028: Park then Unpark after any mode change.
        """
        self.set_dmd_park(True)
        time.sleep(0.15)
        self.set_dmd_park(False)
        time.sleep(0.15)

    # ---- triggers ---
    def configure_trigger_out_1(self, polarity_high: bool=True, rising_delay_us: int=0, falling_delay_us: int=20):
        """
        Sets the configuration for Trigger Out 1.

        Args:
            polarity_high (bool, optional): Polarity of the trigger output, where high is `True` and low is `False`. Defaults to True.
            rising_delay_us (int, optional): The rising delay in microseconds. Defaults to 0.
            falling_delay_us (int, optional): The falling delay in microseconds. Defaults to 20.
        """
        b0 = 0 if polarity_high else 1
        self._write(0x1A1D, struct.pack("<Bhh", b0, rising_delay_us, falling_delay_us))

    def configure_trigger_out_2(self, polarity_high: bool=True, rising_delay_us: int=0, falling_delay_us: int=20):
        """
        Sets the configuration for Trigger Out 2.

        Args:
            polarity_high (bool, optional): Polarity of the trigger output, where high is `True` and low is `False`. Defaults to True.
            rising_delay_us (int, optional): The rising delay in microseconds. Defaults to 0.
            falling_delay_us (int, optional): The falling delay in microseconds. Defaults to 20.
        """
        b0 = 0 if polarity_high else 1
        self._write(0x1A1E, struct.pack("<Bhh", b0, rising_delay_us, falling_delay_us))

    # ---- pattern sequencer ---
    def start_pattern_display(self, mode: int):
        """
        Start or stop the pattern display sequencer.
        
        **Mode Options** 
        - `0`: stop
        - `1`: pause
        - `2`: start
        
        Args:
            mode (int): The mode to set for the pattern display sequencer.
        """
        self._write(0x1A24, struct.pack("<B", mode))

    def set_pattern_lut_config(self, num_entries: int, repeat: bool=True):
        """
        0x1A31: LUT entry count + repeat-count (0 = infinite).
        
        Args:
            num_entries (int): The number of LUT entries.
            repeat (bool, optional): Whether to repeat the pattern display. Defaults to True.
        """
        num_to_display = 0 if repeat else num_entries
        self._write(0x1A31, struct.pack("<HI", num_entries, num_to_display))

    def set_pattern_lut_definition(self, entries: Sequence[LutEntry]):
        """
        0x1A34: Define pattern LUT entries (DLPU018J Table 2-143).

        Entries are `LutEntry` objects from the runtime layer. In streaming
        Video Pattern Mode the image pattern index is normally zero, but the
        selected video bit/frame position remains meaningful.
        
        Args:
            entries (Sequence[LutEntry]): A sequence of `LutEntry` objects defining the pattern LUT entries.
        """
        for entry in entries:
            pattern_index = int(entry.pattern_index)
            exp_us = int(entry.exposure_us)
            dark_us = int(entry.dark_us)
            depth = int(entry.bit_depth)
            led = int(entry.led_select)
            bit_pos = int(entry.bit_position)
            image_pattern_index = int(entry.image_pattern_index)
            wait_for_trigger = bool(getattr(entry, "wait_for_trigger", False))

            ext_depth = 1 if depth > 8 else 0
            depth_field = (depth - 1) & 0x07
            exp3 = struct.pack("<I", exp_us)[:3]
            dark3 = struct.pack("<I", dark_us)[:3]
            b5 = ((0x80 if wait_for_trigger else 0) | (1 if entry.clear_after else 0) | (depth_field << 1) | ((led & 0x07) << 4))
            b9 = (1 if entry.trig2_disabled else 0) | ((ext_depth & 0x01) << 1)
            b1011 = ((bit_pos & 0x1F) << 11) | (image_pattern_index & 0x07FF)

            entry_payload = (
                struct.pack("<H",
                            pattern_index) + exp3 + struct.pack("<B",
                                                                b5) + dark3 + struct.pack("<B",
                                                                                          b9) +
                struct.pack("<H",
                            b1011))
            self._write(0x1A34, entry_payload)

    # --- misc ---
    def wake_displayport_receiver(self):
        """
        Wake DisplayPort receiver.
        """
        self._write(0x1A01, bytes([2]))

    def set_input_pixel_format(self, pixel_format: int):
        """
        Sets the input pixel format.

        Args:
            pixel_format (int): The input pixel format.
        """
        self._write(0x1A02, struct.pack("<B", pixel_format))

    def set_internal_test_pattern_color(self, foreground: int, background: int | None = None):
        """
        Sets the color of the internal test pattern.

        Args:
            foreground (int): The foreground color.
            background (int | None, optional): The background color. Defaults to None.
        """
        background = foreground if background is None else background
        self._write(
            0x1204,
            struct.pack(
                "<HHHHHH",
                foreground,
                foreground,
                foreground,
                background,
                background,
                background,
            ),
        )

    def set_internal_test_pattern(self, pattern: int):
        """
        Sets the internal test pattern.

        Args:
            pattern (int): The internal test pattern.
        """
        self._write(0x1203, struct.pack("<B", pattern))
