"""
DLPC900 USB HID driver — pycrafter6500 protocol.

Key protocol change vs prior implementation:
  Write flag 0x40 (ACK requested) instead of 0x00 (fire-and-forget).
  Every command drains the firmware response before returning, giving
  implicit flow control identical to pycrafter6500_modified.py.

Packet layout (DLPU018J §1.2):
  Byte 0      flag   0x40 = write+ACK, 0xC0 = read+reply
  Byte 1      seq    auto-incrementing counter
  Bytes 2-3   plen   2 (cmd bytes) + len(data), little-endian
  Byte 4      cmd LSB
  Byte 5      cmd MSB
  Bytes 6+    data payload
"""

import struct
import time
from typing import cast

import usb.core
import usb.util

from logger import logger


class DLPC900:
    VID = 0x0451
    PID = 0xC900

    def __init__(self):
        try:
            found = usb.core.find(idVendor=self.VID, idProduct=self.PID)
        except Exception as e:
            logger.critical(f"[DLPC900] USB backend error: {e}")
            raise RuntimeError(f"USB backend error: {e}")

        if found is None:
            logger.critical("[DLPC900] Device not found on USB bus.")
            raise ValueError("DLPC900 not found on USB bus")

        self.dev = cast(usb.core.Device, found)

        for intf in (0, 1):
            try:
                if self.dev.is_kernel_driver_active(intf):
                    self.dev.detach_kernel_driver(intf)
            except Exception:
                pass

        self.dev.set_configuration()

        # Dynamic HID interface enum (Finding 47): DLPC900 is composite USB.
        # Linux frequently puts HID on intf 1; Windows on intf 0. Hard-coded 0
        # caused silent endpoint mismatch on Linux. Find first intf with class=3.
        cfg = self.dev.get_active_configuration()
        hid_intf = None
        for intf in cfg:
            if intf.bInterfaceClass == 0x03:
                hid_intf = intf.bInterfaceNumber
                break
        if hid_intf is None:
            hid_intf = 0
        self._hid_intf = hid_intf
        logger.debug(f"[DLPC900] Claiming HID interface {hid_intf}")
        usb.util.claim_interface(self.dev, hid_intf)
        self._seq = 0

    def _seq_next(self):
        v = self._seq & 0xFF
        self._seq = (self._seq + 1) & 0xFF
        return v

    def _command(self, read: bool, cmd_id: int, data: bytes = b""):
        """Send a command and drain the response.

        Uses flag 0x40 for writes (ACK requested) and 0xC0 for reads,
        matching the pycrafter6500_modified.py protocol exactly.  The
        firmware ACK/response is always consumed before returning so the
        IN endpoint never accumulates stale packets.
        """
        flag = 0xC0 if read else 0x40
        seq = self._seq_next()
        plen = 2 + len(data)

        # Build full packet: header + data, then split into 64-byte frames.
        buf = bytearray([
            flag, seq,
            plen & 0xFF, (plen >> 8) & 0xFF,
            cmd_id & 0xFF,          # LSB → byte 4
            (cmd_id >> 8) & 0xFF,   # MSB → byte 5
        ])
        buf.extend(data)

        for off in range(0, max(len(buf), 1), 64):
            chunk = bytes(buf[off : off + 64]).ljust(64, b"\x00")
            try:
                self.dev.write(0x01, chunk, timeout=2000)
            except usb.core.USBError:
                time.sleep(0.1)
                self.dev.write(0x01, chunk)

        # Drain the firmware response (ACK for writes, payload for reads).
        # Poll up to 6 packets; match on sequence byte.
        # Timeout 2000ms (Finding 48): 500ms too short for multi-packet ACKs.
        #
        # Report-ID detection: some USB HID stacks prepend a 0x00 byte.
        # With our flag values (0x40 write-ACK, 0xC0 read-reply), the real
        # flag byte is never 0x00, so r[0]==0x00 reliably signals a prefix.
        resp = None
        last_resp = None
        for _ in range(6):
            try:
                r = bytes(self.dev.read(0x81, 64, timeout=2000))
            except Exception:
                break
            base = 1 if (len(r) >= 2 and r[0] == 0x00) else 0
            if len(r) > base + 1:
                stripped = bytes(r[base:])
                last_resp = stripped
                if stripped[1] == seq:
                    resp = stripped
                    break

        # NACK detection (TI: hidMessageStruct.head.flags.nack = bit 5).
        # Firmware sets this when the command fails validation. Surfacing the
        # error makes silent spec-violation NACKs visible in logs instead of
        # being treated as success — matches TI's LCR_Write(ackRequired) check.
        if resp is not None and (resp[0] & 0x20):
            logger.warning(
                f"[NACK] Firmware rejected cmd 0x{cmd_id:04X} (flags=0x{resp[0]:02X}). "
                "Check command validity for current display mode."
            )

        # Fall back to last received packet if seq never matched
        # (mirrors old send_read behaviour — prevents None from propagating
        # into _payload when the firmware is slightly slow).
        return resp if resp is not None else last_resp

    def _write(self, cmd_id: int, data: bytes = b""):
        self._command(False, cmd_id, data)

    def _read(self, cmd_id: int):
        return self._command(True, cmd_id, b"")

    def _payload(self, resp, min_len: int = 1):
        """Extract data payload from a read response.

        Handles two firmware layouts:
          [flag, seq, lenL, lenH, cmdL, cmdH, data...]  (with command echo)
          [flag, seq, lenL, lenH, data...]               (no command echo)
        """
        if resp is None or len(resp) < 4:
            return None
        plen = resp[2] | (resp[3] << 8)
        if plen == 0:
            return b""
        # With command echo: data starts at byte 6, length = plen - 2.
        if len(resp) >= 7 and plen >= 2:
            d = resp[6 : 6 + (plen - 2)]
            if len(d) >= min_len:
                return d
        # Without command echo: data starts at byte 4, length = plen.
        d = resp[4 : 4 + plen]
        return d if len(d) >= min_len else None

    # ---- status / diagnostic -----------------------------------------

    def get_display_mode(self):
        resp = self._read(0x1A1B)
        p = self._payload(resp)
        return (p[0], None) if p else (None, None)

    def get_hardware_status(self):
        resp = self._read(0x1A0A)
        p = self._payload(resp)
        return p[0] if p else None

    def get_last_error(self):
        resp = self._read(0x0100)
        p = self._payload(resp)
        return p[0] if p else None

    def get_main_status(self):
        resp = self._read(0x1A0C)
        p = self._payload(resp)
        if p:
            v = p[0]
            return {
                "dmd_parked":            bool(v & 0x01),
                "sequencer_running":     bool(v & 0x02),
                "video_frozen":          bool(v & 0x04),
                "external_source_locked":bool(v & 0x08),
                "port1_syncs_valid":     bool(v & 0x10),
                "port2_syncs_valid":     bool(v & 0x20),
                "raw": hex(v),
            }
        return None

    def get_firmware_version(self):
        """0x0205: 16-byte response. Returns dict with app/api/swcfg/seqcfg versions.

        Per DLPU018J Table 2-12, each version is 4 bytes:
          [patch_lo, patch_hi, minor, major]
        """
        resp = self._read(0x0205)
        p = self._payload(resp, min_len=16)
        if not p or len(p) < 16:
            return None
        def _ver(buf):
            return {
                "major": buf[3],
                "minor": buf[2],
                "patch": buf[0] | (buf[1] << 8),
                "str": f"{buf[3]}.{buf[2]}.{buf[0] | (buf[1] << 8)}",
            }
        return {
            "app":     _ver(p[0:4]),
            "api":     _ver(p[4:8]),
            "sw_cfg":  _ver(p[8:12]),
            "seq_cfg": _ver(p[12:16]),
        }

    def get_channel_swap(self):
        """0x1A37: Returns channel-swap config byte.

        Bit 0 = port (0=P1, 1=P2). Bits 3:1 = swap mode:
          0=ABC, 1=CAB, 2=BCA, 3=ACB, 4=BAC, 5=CBA (DLPU018J Table 2-50).
        Default reset = 0x8 (port=0, swap=4 = BAC = A/B swapped).
        """
        resp = self._read(0x1A37)
        p = self._payload(resp)
        if not p:
            return None
        v = p[0]
        port = v & 0x01
        swap = (v >> 1) & 0x07
        labels = {0: "ABC", 1: "CAB", 2: "BCA", 3: "ACB", 4: "BAC", 5: "CBA"}
        return {
            "raw": hex(v),
            "port": f"P{port + 1}",
            "swap_code": swap,
            "swap_label": labels.get(swap, f"Unknown({swap})"),
        }

    def get_display_dimensions(self):
        resp = self._read(0x1A3C)
        p = self._payload(resp, min_len=18)
        if p and len(p) >= 18:
            return {
                "total_pixels_per_line":   struct.unpack_from("<H", p, 0)[0],
                "total_lines_per_frame":   struct.unpack_from("<H", p, 2)[0],
                "active_pixels_per_line":  struct.unpack_from("<H", p, 4)[0],
                "active_lines_per_frame":  struct.unpack_from("<H", p, 6)[0],
                "first_active_pixel":      struct.unpack_from("<H", p, 8)[0],
                "first_active_line":       struct.unpack_from("<H", p, 10)[0],
                "bottom_field_first_line": struct.unpack_from("<H", p, 12)[0],
                "pixel_clock_khz":         struct.unpack_from("<I", p, 14)[0],
            }
        return None

    def get_port_config(self):
        resp = self._read(0x1A03)
        p = self._payload(resp)
        if p:
            v = p[0]
            modes = {0: "Single Pixel Port 1", 1: "Single Pixel Port 2",
                     2: "Dual Pixel P1-P2",    3: "Dual Pixel P2-P1"}
            return {
                "pixel_mode":   modes.get(v & 0x03, f"Unknown({v & 0x03})"),
                "pixel_clock":  f"Clock {((v >> 2) & 0x03) + 1}",
                "data_enable":  f"DE {((v >> 4) & 0x01) + 1}",
                "sync_select":  f"P{((v >> 5) & 0x01) + 1} VSync/HSync",
                "raw": hex(v),
            }
        return None

    def get_trigger_out_1(self):
        resp = self._read(0x1A1D)
        p = self._payload(resp, min_len=5)
        if p and len(p) >= 5:
            return {
                "polarity":        "Inverted" if p[0] & 0x01 else "Non-inverted",
                "rising_delay_us":  struct.unpack_from("<h", p, 1)[0],
                "falling_delay_us": struct.unpack_from("<h", p, 3)[0],
                "raw": p.hex(),
            }
        return {"raw": p.hex() if p else "NO_RESPONSE"}

    def get_trigger_out_2(self):
        resp = self._read(0x1A1E)
        p = self._payload(resp, min_len=5)
        if p and len(p) >= 5:
            return {
                "polarity":        "Inverted" if p[0] & 0x01 else "Non-inverted",
                "rising_delay_us":  struct.unpack_from("<h", p, 1)[0],
                "falling_delay_us": struct.unpack_from("<h", p, 3)[0],
                "raw": p.hex(),
            }
        return {"raw": p.hex() if p else "NO_RESPONSE"}

    # ---- mode / source -----------------------------------------------

    def set_display_mode(self, mode):
        self._write(0x1A1B, struct.pack("<B", mode))

    def set_input_source(self, source=0, bit_depth_sel=1):
        val = (source & 0x07) | ((bit_depth_sel & 0x03) << 3)
        self._write(0x1A00, struct.pack("<B", val))

    def set_port_config(self, pixel_mode=2, pixel_clock=0, data_enable=0, sync_select=0):
        val = (
            (pixel_mode  & 0x03)
            | ((pixel_clock  & 0x03) << 2)
            | ((data_enable  & 0x01) << 4)
            | ((sync_select  & 0x01) << 5)
        )
        self._write(0x1A03, struct.pack("<B", val))

    def toggle_dual_pixel_mode(self, enable):
        self.set_port_config(pixel_mode=(2 if enable else 0),
                             pixel_clock=0, data_enable=0, sync_select=0)

    def set_input_display_resolution(self, in_x, in_y, in_w, in_h,
                                     out_x=None, out_y=None, out_w=None, out_h=None):
        out_x = in_x if out_x is None else out_x
        out_y = in_y if out_y is None else out_y
        out_w = in_w if out_w is None else out_w
        out_h = in_h if out_h is None else out_h
        self._write(0x1000, struct.pack("<HHHHHHHH",
                                       in_x, in_y, in_w, in_h,
                                       out_x, out_y, out_w, out_h))

    # ---- LEDs --------------------------------------------------------

    def set_led_enables(self, r=True, g=True, b=True, sequencer=True):
        val = (1 if r else 0) | ((1 if g else 0) << 1) | ((1 if b else 0) << 2)
        if sequencer:
            val |= 0x08
        self._write(0x1A07, struct.pack("<B", val))

    def set_led_current(self, r=255, g=255, b=255):
        self._write(0x0B01, struct.pack("<BBB", r, g, b))

    # ---- DMD park ----------------------------------------------------

    def set_dmd_park(self, park):
        self._write(0x0609, struct.pack("<B", 1 if park else 0))

    def apply_block_lock_workaround(self):
        """DLPT028: Park then Unpark after any mode change."""
        self.set_dmd_park(True)
        time.sleep(0.15)
        self.set_dmd_park(False)
        time.sleep(0.15)

    # ---- triggers ----------------------------------------------------

    def configure_trigger_out_1(self, polarity_high=True,
                                 rising_delay_us=0, falling_delay_us=20):
        b0 = 0 if polarity_high else 1
        self._write(0x1A1D, struct.pack("<Bhh", b0, rising_delay_us, falling_delay_us))

    def configure_trigger_out_2(self, polarity_high=True,
                                 rising_delay_us=0, falling_delay_us=20):
        b0 = 0 if polarity_high else 1
        self._write(0x1A1E, struct.pack("<Bhh", b0, rising_delay_us, falling_delay_us))

    # ---- pattern sequencer -------------------------------------------

    def start_pattern_display(self, mode):
        """mode: 0=stop, 1=pause, 2=start."""
        self._write(0x1A24, struct.pack("<B", mode))

    def set_pattern_lut_config(self, num_entries, repeat=True):
        """0x1A31: LUT entry count + repeat-count (0 = infinite)."""
        num_to_display = 0 if repeat else num_entries
        self._write(0x1A31, struct.pack("<HI", num_entries, num_to_display))

    def set_pattern_lut_reorder(self, order, repeat=True):
        """0x1A32: Reorder LUT playback sequence for Pattern Mode.""" 
        order_list = [int(idx) for idx in order]
        if not order_list:
            raise ValueError("Pattern LUT reorder list cannot be empty")
        for idx in order_list:
            if not (0 <= idx <= 399):
                raise ValueError(f"Reorder index out of range: {idx}")
        nr = len(order_list)
        np_ = 0 if repeat else nr
        payload = struct.pack("<HI", nr, np_)
        payload += b"".join(struct.pack("<H", idx) for idx in order_list)
        self._write(0x1A32, payload)

    def set_pattern_lut_definition(self, entries):
        """0x1A34: Define pattern LUT entries (DLPU018J Table 2-143).

        entry = (idx, exp_us, clear, depth, led, dark_us, trig2_disable, bit_pos)
        optional 9th element: image_index (default 0, unused in Video Pattern Mode)

        Finding 42: Send 24 separate 12-byte 0x1A34 commands (one per entry),
        matching TI's LCR_SendPatLut(). Old code concatenated all entries into
        one 288-byte payload spanning 5 HID packets — protocol-divergent and
        relied on firmware to correctly buffer fragmented mega-payload.
        """
        for entry in entries:
            if len(entry) == 8:
                idx, exp_us, clear, depth, led, dark_us, trig2_disable, bit_pos = entry
                image_index = 0
            elif len(entry) == 9:
                idx, exp_us, clear, depth, led, dark_us, trig2_disable, bit_pos, image_index = entry
            else:
                raise ValueError("Each LUT entry must have 8 or 9 elements")

            idx = int(idx)
            exp_us = int(exp_us)
            dark_us = int(dark_us)
            depth = int(depth)
            led = int(led)
            bit_pos = int(bit_pos)
            image_index = int(image_index)

            ext_depth   = 1 if depth > 8 else 0
            depth_field = (depth - 1) & 0x07
            exp3        = struct.pack("<I", exp_us)[:3]
            dark3       = struct.pack("<I", dark_us)[:3]
            b5          = (1 if clear else 0) | (depth_field << 1) | ((led & 0x07) << 4)
            b9          = (1 if trig2_disable else 0) | ((ext_depth & 0x01) << 1)
            b1011       = (image_index & 0x07FF) | ((bit_pos & 0x1F) << 11)

            entry_payload = (
                struct.pack("<H", idx)
                + exp3
                + struct.pack("<B", b5)
                + dark3
                + struct.pack("<B", b9)
                + struct.pack("<H", b1011)
            )
            self._write(0x1A34, entry_payload)

    # ---- misc --------------------------------------------------------

    def set_internal_test_pattern(self, pattern):
        self._write(0x1203, struct.pack("<B", pattern))

    def send_packet(self, cmd_id: int, data: bytes = b"", read: bool = False):
        """Backward-compat shim: routes to _read or _write."""
        if read:
            return self._read(cmd_id)
        self._write(cmd_id, data)
