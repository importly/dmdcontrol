from dmdcontrol.runtime import video_pattern


class FakeDLPC900:
    def __init__(self):
        self.calls = []
        self.display_mode = 0

    def get_hardware_status(self):
        return 0

    def get_last_error(self):
        return 0

    def get_error_description(self):
        return ""

    def get_display_mode(self):
        return self.display_mode, None

    def set_led_current(self, red, green, blue):
        self.calls.append(("set_led_current", red, green, blue))

    def set_led_enables(self, red, green, blue, *, sequencer=False):
        self.calls.append(("set_led_enables", red, green, blue, sequencer))

    def set_display_mode(self, mode):
        self.display_mode = mode
        self.calls.append(("set_display_mode", mode))

    def set_input_source(self, source, bit_depth_sel):
        self.calls.append(("set_input_source", source, bit_depth_sel))

    def set_input_pixel_format(self, pixel_format):
        self.calls.append(("set_input_pixel_format", pixel_format))

    def set_data_channel_swap(self, port, swap):
        self.calls.append(("set_data_channel_swap", port, swap))

    def toggle_dual_pixel_mode(self, enabled):
        self.calls.append(("toggle_dual_pixel_mode", enabled))

    def set_input_display_resolution(self, x, y, width, height):
        self.calls.append(("set_input_display_resolution", x, y, width, height))

    def apply_block_lock_workaround(self):
        self.calls.append(("apply_block_lock_workaround",))

    def start_pattern_display(self, action):
        self.calls.append(("start_pattern_display", action))

    def get_main_status(self):
        return {
            "external_source_locked": True,
            "port1_syncs_valid": True,
            "video_frozen": False,
        }

    def configure_trigger_out_1(self, *, polarity_high, rising_delay_us, falling_delay_us):
        self.calls.append(("configure_trigger_out_1", polarity_high, rising_delay_us, falling_delay_us))

    def configure_trigger_out_2(self, *, polarity_high, rising_delay_us, falling_delay_us):
        self.calls.append(("configure_trigger_out_2", polarity_high, rising_delay_us, falling_delay_us))

    def get_display_dimensions(self):
        return None

    def get_trigger_out_1(self):
        return None

    def get_trigger_out_2(self):
        return None


def test_video_pattern_setup_sets_rgb_format_and_evm_channel_swap(monkeypatch):
    dlpc = FakeDLPC900()
    sleep_calls = []
    stable_calls = []
    monkeypatch.setattr(video_pattern.time, "sleep", sleep_calls.append)
    monkeypatch.setattr(video_pattern, "wait_for_external_lock", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        video_pattern,
        "wait_for_stable_external_lock",
        lambda *_args, **kwargs: stable_calls.append(kwargs) or True,
    )
    monkeypatch.setattr(video_pattern, "ensure_video_pattern_mode", lambda *_args, **_kwargs: True)

    state = video_pattern.prepare_dlpc900_for_video_pattern(
        dlpc,
        target_hz=60,
        entries_count=1,
        per_entry_exposure_us=1000,
    )

    assert state["entries"][0].wait_for_trigger is True
    assert ("set_input_source", 0, 1) in dlpc.calls
    assert ("set_input_pixel_format", 0) in dlpc.calls
    assert ("set_data_channel_swap", 0, 4) in dlpc.calls
    assert dlpc.calls.index(("set_input_source", 0, 1)) < dlpc.calls.index(("set_input_pixel_format", 0))
    assert dlpc.calls.index(("set_input_pixel_format", 0)) < dlpc.calls.index(("set_data_channel_swap", 0, 4))
    assert dlpc.calls.index(("set_data_channel_swap", 0, 4)) < dlpc.calls.index(("toggle_dual_pixel_mode", False))
    assert 0.5 in sleep_calls
    assert 3 not in sleep_calls
    assert 2.0 not in sleep_calls
    assert 1.0 not in sleep_calls
    assert [call["timeout_s"] for call in stable_calls] == [3.0, 2.0, 1.0]
    assert [call["required_mode"] for call in stable_calls] == [0, 2, 2]