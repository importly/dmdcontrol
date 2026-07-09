import struct

from dmdcontrol.hardware.dlpc900 import DLPC900
from dmdcontrol.runtime.lifecycle import LutEntry


def _capture_pattern_lut_writes(entries):
    controller = DLPC900.__new__(DLPC900)
    writes = []

    def fake_write(cmd_id, payload):
        writes.append((cmd_id, payload))

    controller._write = fake_write
    controller.set_pattern_lut_definition(entries)
    return writes


def _decode_payload(payload):
    packed_10_11 = struct.unpack("<H", payload[10:12])[0]
    return {
        "pattern_index": struct.unpack("<H", payload[0:2])[0],
        "exposure_us": int.from_bytes(payload[2:5] + b"\x00", "little"),
        "flags": payload[5],
        "dark_us": int.from_bytes(payload[6:9] + b"\x00", "little"),
        "trigger_flags": payload[9],
        "image_pattern_index": packed_10_11 & 0x07FF,
        "bit_position": (packed_10_11 >> 11) & 0x1F,
    }


def test_pattern_lut_definition_packs_ti_video_pattern_fields():
    entries = [
        LutEntry(
            pattern_index=0,
            exposure_us=200,
            clear_after=False,
            bit_depth=1,
            led_select=1,
            dark_us=0,
            trig2_disabled=False,
            bit_position=0,
            image_pattern_index=0,
            wait_for_trigger=True,
        ),
        LutEntry(
            pattern_index=1,
            exposure_us=400,
            clear_after=True,
            bit_depth=1,
            led_select=2,
            dark_us=0,
            trig2_disabled=False,
            bit_position=1,
            image_pattern_index=0,
        ),
    ]

    writes = _capture_pattern_lut_writes(entries)

    assert [cmd_id for cmd_id, _payload in writes] == [0x1A34, 0x1A34]
    assert _decode_payload(writes[0][1]) == {
        "pattern_index": 0,
        "exposure_us": 200,
        "flags": 0x90,
        "dark_us": 0,
        "trigger_flags": 0,
        "image_pattern_index": 0,
        "bit_position": 0,
    }
    assert _decode_payload(writes[1][1]) == {
        "pattern_index": 1,
        "exposure_us": 400,
        "flags": 0x21,
        "dark_us": 0,
        "trigger_flags": 0,
        "image_pattern_index": 0,
        "bit_position": 1,
    }


def test_pattern_lut_definition_allows_duplicate_selected_bit_position():
    entries = [
        LutEntry(
            pattern_index=0,
            exposure_us=1000,
            clear_after=False,
            bit_depth=1,
            led_select=7,
            dark_us=0,
            trig2_disabled=False,
            bit_position=3,
            image_pattern_index=0,
        ),
        LutEntry(
            pattern_index=1,
            exposure_us=2000,
            clear_after=True,
            bit_depth=1,
            led_select=7,
            dark_us=50,
            trig2_disabled=True,
            bit_position=3,
            image_pattern_index=0,
        ),
    ]

    writes = _capture_pattern_lut_writes(entries)
    first = _decode_payload(writes[0][1])
    second = _decode_payload(writes[1][1])

    assert first["pattern_index"] == 0
    assert second["pattern_index"] == 1
    assert first["bit_position"] == 3
    assert second["bit_position"] == 3
    assert first["image_pattern_index"] == 0
    assert second["image_pattern_index"] == 0
    assert second["dark_us"] == 50
    assert second["trigger_flags"] == 1


def test_pattern_lut_definition_packs_frame_change_wait_for_trigger_bit():
    entries = [
        LutEntry(
            pattern_index=0,
            exposure_us=105,
            clear_after=False,
            bit_depth=1,
            led_select=7,
            dark_us=0,
            trig2_disabled=False,
            bit_position=0,
            image_pattern_index=0,
            wait_for_trigger=True,
        ),
        LutEntry(
            pattern_index=1,
            exposure_us=105,
            clear_after=False,
            bit_depth=1,
            led_select=7,
            dark_us=0,
            trig2_disabled=False,
            bit_position=1,
            image_pattern_index=0,
            wait_for_trigger=False,
        ),
    ]

    writes = _capture_pattern_lut_writes(entries)

    assert _decode_payload(writes[0][1])["flags"] & 0x80
    assert not (_decode_payload(writes[1][1])["flags"] & 0x80)

def test_pattern_lut_definition_packs_frame_change_bit_position_separate_from_pattern_index():
    entry = LutEntry(
        pattern_index=1,
        exposure_us=105,
        clear_after=False,
        bit_depth=1,
        led_select=7,
        dark_us=0,
        trig2_disabled=False,
        bit_position=8,
        image_pattern_index=0,
    )

    writes = _capture_pattern_lut_writes([entry])
    decoded = _decode_payload(writes[0][1])

    assert writes[0][0] == 0x1A34
    assert writes[0][1][0:2] == struct.pack("<H", 1)
    assert writes[0][1][10:12] == struct.pack("<H", 8 << 11)
    assert decoded["pattern_index"] == 1
    assert decoded["bit_position"] == 8
    assert decoded["image_pattern_index"] == 0


def test_data_channel_swap_writes_evm_bac_payload():
    controller = DLPC900.__new__(DLPC900)
    writes = []
    controller._write = lambda cmd_id, payload: writes.append((cmd_id, payload))

    controller.set_data_channel_swap(port=0, swap=4)

    assert writes == [(0x1A37, b"\x08")]