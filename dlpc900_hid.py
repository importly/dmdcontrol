import usb.core
import usb.util
import struct
import time
from logger import logger


class DLPC900:
    """
    DLPC900 USB HID driver.  DLPU018J §1.2

    64-byte packet layout (DLPU018J §1.2):
      Byte 0      : Flag  (0x00=write, 0xC0=read+reply)
      Byte 1      : Sequence counter
      Bytes 2-3   : Length = 2 (cmd) + len(data)
      Bytes 4-5   : USB Command LSB, MSB
      Bytes 6+    : Data
    """

    VID = 0x0451
    PID = 0xC900

    def __init__(self):
        try:
            self.dev = usb.core.find(idVendor=self.VID, idProduct=self.PID)
        except Exception as e:
            logger.critical(f"[DLPC900] USB backend error during initialization: {e}")
            raise RuntimeError(f"USB backend error: {e}")

        if self.dev is None:
            logger.critical(
                "[DLPC900] Device not found on USB bus. Ensure it is powered on and connected."
            )
            raise ValueError("DLPC900 not found on USB bus")

        for intf_num in (0, 1):
            try:
                if self.dev.is_kernel_driver_active(intf_num):
                    self.dev.detach_kernel_driver(intf_num)
            except Exception:
                pass

        self.dev.set_configuration()
        usb.util.claim_interface(self.dev, 0)

        self.ep_out = 0x01
        self.ep_in = 0x81
        self._seq = 0

    def _seq_next(self):
        v = self._seq & 0xFF
        self._seq = (self._seq + 1) & 0xFF
        return v

    def send_packet(self, cmd_id, data=b"", read=False):
        # DLPU018J §1.2.3:
        #   write: bit7=0, bit6=0 -> 0x00
        #   read : bit7=1, bit6=1 -> 0xC0
        flag = 0xC0 if read else 0x00
        seq = self._seq_next()
        # Length = 2-byte command + data  (DLPU018 §1.2.1)
        plen = 2 + len(data)
        hdr = (
            bytes(
                [
                    flag,
                    seq,
                    plen & 0xFF,
                    (plen >> 8) & 0xFF,
                    cmd_id & 0xFF,
                    (cmd_id >> 8) & 0xFF,
                ]
            )
            + data
        )

        # Pad/split into 64-byte frames
        for off in range(0, max(len(hdr), 1), 64):
            chunk = hdr[off : off + 64]
            chunk += b"\x00" * (64 - len(chunk))
            try:
                self.dev.write(self.ep_out, chunk, timeout=500)
            except usb.core.USBError as e:
                # Board occasionally drops packets and times out. Retry once per WetenSchaap.
                time.sleep(0.1)
                try:
                    self.dev.write(self.ep_out, chunk, timeout=500)
                except usb.core.USBError as e2:
                    logger.error(f"[DLPC900] USB write error after retry: {e2}")
                    raise
        return seq

    def read_response(self, timeout=1000):
        try:
            return bytes(self.dev.read(self.ep_in, 64, timeout=timeout))
        except Exception:
            return None

    def _response_base(self, resp):
        if not resp or len(resp) < 4:
            return None
        # Some stacks include HID report ID (0x00) as first byte.
        if len(resp) >= 5 and resp[0] == 0x00 and (resp[1] & 0x80):
            return 1
        return 0

    def _response_seq(self, resp):
        base = self._response_base(resp)
        if base is None or len(resp) < base + 2:
            return None
        return resp[base + 1]

    def _response_payload(self, resp, cmd_id=None):
        """Extract data payload from a read response.

        Handles both observed layouts:
          - [flag, seq, lenL, lenH, cmdL, cmdH, data...]
          - [flag, seq, lenL, lenH, data...]
        and optional leading report-id byte.
        """
        base = self._response_base(resp)
        if base is None or len(resp) < base + 4:
            return b""

        plen = resp[base + 2] | (resp[base + 3] << 8)
        if plen < 0:
            return b""

        # Preferred: command echo present and matches expected command.
        if cmd_id is not None and len(resp) >= base + 6:
            cmd_l = cmd_id & 0xFF
            cmd_h = (cmd_id >> 8) & 0xFF
            if resp[base + 4] == cmd_l and resp[base + 5] == cmd_h:
                data_start = base + 6
                # Some firmwares report length = command + data, others = data only.
                cands = []
                if plen >= 2:
                    cands.append(plen - 2)
                cands.append(plen)
                for data_len in cands:
                    if data_len <= 0:
                        continue
                    data_end = min(len(resp), data_start + data_len)
                    if data_end > data_start:
                        return resp[data_start:data_end]
                return b""

        # Fallback: no command echo in response.
        data_start = base + 4
        if plen == 0:
            return b""
        data_end = min(len(resp), data_start + plen)
        return resp[data_start:data_end]

    def send_read(self, cmd_id):
        seq = self.send_packet(cmd_id, b"", read=True)
        # Match sequence byte to avoid stale buffered packets.
        last_resp = None
        for _ in range(6):
            resp = self.read_response()
            if resp is None:
                continue
            last_resp = resp
            rsp_seq = self._response_seq(resp)
            if rsp_seq is None:
                continue
            if rsp_seq == seq:
                return resp
        return last_resp

    # ---- diagnostic --------------------------------------------------
    def get_display_mode(self):
        r = self.send_read(0x1A1B)
        payload = self._response_payload(r, 0x1A1B)
        if payload:
            base = self._response_base(r)
            flag = r[base] if base is not None and len(r) > base else 0
            return payload[0], (flag >> 5) & 1
        return None, None

    def get_hardware_status(self):
        r = self.send_read(0x1A0A)
        payload = self._response_payload(r, 0x1A0A)
        return payload[0] if payload else None

    def get_last_error(self):
        r = self.send_read(0x0100)
        payload = self._response_payload(r, 0x0100)
        return payload[0] if payload else None

    # ---- mode / source -----------------------------------------------
    def set_display_mode(self, mode):
        self.send_packet(0x1A1B, struct.pack("<B", mode))

    def set_input_source(self, source=0, bit_depth_sel=1):
        val = (source & 0x07) | ((bit_depth_sel & 0x03) << 3)
        self.send_packet(0x1A00, struct.pack("<B", val))

    def set_port_config(
        self, pixel_mode=2, pixel_clock=0, data_enable=0, sync_select=0
    ):
        """Set 0x1A03 Port/Clock config (DLPU018J Table 2-52)."""
        val = (
            (pixel_mode & 0x03)
            | ((pixel_clock & 0x03) << 2)
            | ((data_enable & 0x01) << 4)
            | ((sync_select & 0x01) << 5)
        )
        self.send_packet(0x1A03, struct.pack("<B", val))
    def configure_trigger_out_1(self, polarity_high=True, rising_delay_us=0, falling_delay_us=20):
        """0x1A1D: Trigger Out 1 Configuration (DLPU018J Table 2-118).

        Byte 0, Bit 0: Polarity (0 = Non-inverted / Active High, 1 = Inverted / Active Low)
        Byte 0, Bits 7:1: Reserved (must be 0)
        Bytes 1-2: Rising edge delay (int16, µs, range -20 to 20000)
        Bytes 3-4: Falling edge delay (int16, µs, range -20 to 20000)

        Constraints:
          Non-inverted: rising_delay <= falling_delay
          Inverted:     rising_delay >= falling_delay
          Minimum pulse width: 20 µs
        """
        b0 = 0 if polarity_high else 1
        payload = struct.pack("<Bhh", b0, rising_delay_us, falling_delay_us)
        self.send_packet(0x1A1D, payload)
        
    def configure_trigger_out_2(self, polarity_high=True, rising_delay_us=0, falling_delay_us=20):
        """0x1A1E: Trigger Out 2 Configuration (DLPU018J Table 2-120).

        Byte 0, Bit 0: Polarity (0 = Non-inverted / Active High, 1 = Inverted / Active Low)
        Byte 0, Bits 7:1: Reserved (must be 0)
        Bytes 1-2: Rising edge delay (int16, µs, range -20 to 20000)
        Bytes 3-4: Falling edge delay (int16, µs, range -20 to 20000)

        Constraints:
          Non-inverted: rising_delay <= falling_delay
          Inverted:     rising_delay >= falling_delay
          Minimum pulse width: 20 µs
        """
        b0 = 0 if polarity_high else 1
        payload = struct.pack("<Bhh", b0, rising_delay_us, falling_delay_us)
        self.send_packet(0x1A1E, payload)

    def get_trigger_out_1(self):
        """Read back 0x1A1D: Trigger Out 1 config."""
        r = self.send_read(0x1A1D)
        payload = self._response_payload(r, 0x1A1D)
        if payload and len(payload) >= 5:
            polarity = payload[0] & 0x01
            rising = struct.unpack_from("<h", payload, 1)[0]
            falling = struct.unpack_from("<h", payload, 3)[0]
            return {
                "polarity": "Inverted" if polarity else "Non-inverted",
                "rising_delay_us": rising,
                "falling_delay_us": falling,
                "raw": payload.hex(),
            }
        return {"raw": payload.hex() if payload else "NO_RESPONSE"}

    def get_trigger_out_2(self):
        """Read back 0x1A1E: Trigger Out 2 config."""
        r = self.send_read(0x1A1E)
        payload = self._response_payload(r, 0x1A1E)
        if payload and len(payload) >= 5:
            polarity = payload[0] & 0x01
            rising = struct.unpack_from("<h", payload, 1)[0]
            falling = struct.unpack_from("<h", payload, 3)[0]
            return {
                "polarity": "Inverted" if polarity else "Non-inverted",
                "rising_delay_us": rising,
                "falling_delay_us": falling,
                "raw": payload.hex(),
            }
        return {"raw": payload.hex() if payload else "NO_RESPONSE"}

    def set_internal_test_pattern(self, pattern):
        # Source must be 1 (internal) first
        self.send_packet(0x1203, struct.pack("<B", pattern))

    # ---- LEDs --------------------------------------------------------
    def set_led_enables(self, r=True, g=True, b=True, sequencer=True):
        val = 1 if r else 0
        val |= (1 if g else 0) << 1
        val |= (1 if b else 0) << 2
        val |= 0x08 if sequencer else 0
        self.send_packet(0x1A07, struct.pack("<B", val))

    def set_led_current(self, r=255, g=255, b=255):
        self.send_packet(0x0B01, struct.pack("<BBB", r, g, b))

    # ---- DMD park ----------------------------------------------------
    def set_dmd_park(self, park):
        self.send_packet(0x0609, struct.pack("<B", 1 if park else 0))

    def apply_block_lock_workaround(self):
        """DLPT028: Park then Unpark after any mode change."""
        self.set_dmd_park(True)
        time.sleep(0.15)
        self.set_dmd_park(False)
        time.sleep(0.15)

    # ---- pattern sequencer -------------------------------------------
    def start_pattern_display(self, mode):
        self.send_packet(0x1A24, struct.pack("<B", mode))

    def set_pattern_lut_config(self, num_entries, repeat=True):
        """0x1A31: num_entries LUT entries, repeat indefinitely."""
        num_to_display = 0 if repeat else num_entries
        self.send_packet(0x1A31, struct.pack("<HI", num_entries, num_to_display))

    def set_pattern_lut_definition(self, entries):
        """
        0x1A34  12 bytes/entry:
          entry = (idx, exp_us, clear, depth, led, dark_us, bit_pos)
        """
        payload = b""
        for idx, exp_us, clear, depth, led, dark_us, bit_pos in entries:
            exp3 = struct.pack("<I", exp_us)[:3]
            dark3 = struct.pack("<I", dark_us)[:3]
            b5 = (1 if clear else 0) | ((depth - 1) << 1) | ((led & 7) << 4)
            # b9: Trigger Out 2 Suppression (DLPU018J Table 2-143).
            # Bit 0: 0 = TRIG_OUT_2 enabled for this pattern, 1 = suppressed.
            # TRIG_OUT_1 is hardwired to frame every pattern exposure; it has no per-LUT control.
            b9 = 0  # Enable TRIG_OUT_2 on every pattern (24 micropulses per frame)
            b1011 = struct.pack("<H", (bit_pos & 0x1F) << 11)
            payload += (
                struct.pack("<H", idx)
                + exp3
                + struct.pack("<B", b5)
                + dark3
                + struct.pack("<B", b9)
                + b1011
            )
        self.send_packet(0x1A34, payload)

    # ---- Windowing / Hardware Crop -----------------------------------
    def set_input_display_resolution(
        self, in_x, in_y, in_w, in_h, out_x=None, out_y=None, out_w=None, out_h=None
    ):
        out_x = in_x if out_x is None else out_x
        out_y = in_y if out_y is None else out_y
        out_w = in_w if out_w is None else out_w
        out_h = in_h if out_h is None else out_h
        self.send_packet(
            0x1000,
            struct.pack(
                "<HHHHHHHH", in_x, in_y, in_w, in_h, out_x, out_y, out_w, out_h
            ),
        )

    def toggle_dual_pixel_mode(self, enable):
        self.set_port_config(
            pixel_mode=(2 if enable else 0), pixel_clock=0, data_enable=0, sync_select=0
        )

    # ---- diagnostic read-back ----------------------------------------
    def get_port_config(self):
        """Read 0x1A03: Port and Clock Configuration (DLPU018J §2.3.3.1)."""
        r = self.send_read(0x1A03)
        payload = self._response_payload(r, 0x1A03)
        if payload:
            val = payload[0]
            pixel_mode = val & 0x03
            pixel_clock = (val >> 2) & 0x03
            data_enable = (val >> 4) & 0x01
            sync_select = (val >> 5) & 0x01
            modes = {
                0: "Single Pixel Port 1",
                1: "Single Pixel Port 2",
                2: "Dual Pixel P1-P2",
                3: "Dual Pixel P2-P1",
            }
            return {
                "pixel_mode": modes.get(pixel_mode, f"Unknown({pixel_mode})"),
                "pixel_clock": f"Clock {pixel_clock + 1}",
                "data_enable": f"DE {data_enable + 1}",
                "sync_select": f"P{sync_select + 1} VSync/HSync",
                "raw": hex(val),
            }
        return None

    def get_display_dimensions(self):
        """Read 0x1A3C: Parallel Port Configuration (DLPU018J §2.3.2.1).
        Returns the board's view of DMD area, active area, pixel clock."""
        r = self.send_read(0x1A3C)
        data = self._response_payload(r, 0x1A3C)
        if data and len(data) >= 18:
            total_w = struct.unpack_from("<H", data, 0)[0]
            total_h = struct.unpack_from("<H", data, 2)[0]
            active_w = struct.unpack_from("<H", data, 4)[0]
            active_h = struct.unpack_from("<H", data, 6)[0]
            first_px = struct.unpack_from("<H", data, 8)[0]
            first_ln = struct.unpack_from("<H", data, 10)[0]
            bot_ln = struct.unpack_from("<H", data, 12)[0]
            pclk_khz = struct.unpack_from("<I", data, 14)[0]
            return {
                "total_pixels_per_line": total_w,
                "total_lines_per_frame": total_h,
                "active_pixels_per_line": active_w,
                "active_lines_per_frame": active_h,
                "first_active_pixel": first_px,
                "first_active_line": first_ln,
                "bottom_field_first_line": bot_ln,
                "pixel_clock_khz": pclk_khz,
            }
        return None

    def get_main_status(self):
        """Read 0x1A0C: Main Status (DLPU018J §2.1.3).
        Returns DMD park state, sequencer run, video lock, port sync validity."""
        r = self.send_read(0x1A0C)
        payload = self._response_payload(r, 0x1A0C)
        if payload:
            val = payload[0]
            return {
                "dmd_parked": bool(val & 0x01),
                "sequencer_running": bool(val & 0x02),
                "video_frozen": bool(val & 0x04),
                "external_source_locked": bool(val & 0x08),
                "port1_syncs_valid": bool(val & 0x10),
                "port2_syncs_valid": bool(val & 0x20),
                "raw": hex(val),
            }
        return None
