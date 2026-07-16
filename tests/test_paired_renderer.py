import logging

import numpy as np
import pytest

from dmdcontrol.patterns import paired
from dmdcontrol.runtime import pair_render


class FakeGL:

    GL_PROJECTION = 1
    GL_MODELVIEW = 2
    GL_TEXTURE_2D = 3
    GL_TEXTURE_MIN_FILTER = 4
    GL_TEXTURE_MAG_FILTER = 5
    GL_TEXTURE_WRAP_S = 6
    GL_TEXTURE_WRAP_T = 7
    GL_NEAREST = 8
    GL_CLAMP_TO_EDGE = 9
    GL_UNPACK_ALIGNMENT = 10
    GL_RGB8 = 11
    GL_RGB = 12
    GL_UNSIGNED_BYTE = 13
    GL_COLOR_BUFFER_BIT = 14
    GL_QUADS = 15

    def __init__(self):
        self.events = []
        self.tex_image_calls = []
        self.tex_sub_image_calls = []
        self.texture_parameter_calls = []
        self.draws = []
        self.deleted_textures = []
        self.bound_texture = None
        self._draw_vertices = None
        self._pending_tex_coord = None

    def glViewport(self, *args):
        self.events.append(("viewport", args))

    def glMatrixMode(self, mode):
        self.events.append(("matrix_mode", mode))

    def glLoadIdentity(self):
        self.events.append(("load_identity", ))

    def glOrtho(self, *args):
        self.events.append(("ortho", args))

    def glEnable(self, target):
        self.events.append(("enable", target))

    def glGenTextures(self, count):
        self.events.append(("gen_textures", count))
        return (101, 202)

    def glBindTexture(self, target, texture):
        self.bound_texture = texture
        self.events.append(("bind_texture", target, texture))

    def glTexParameteri(self, target, parameter, value):
        self.texture_parameter_calls.append(
            (self.bound_texture, target, parameter, value))

    def glPixelStorei(self, parameter, value):
        self.events.append(("pixel_store", parameter, value))

    def glTexImage2D(
        self,
        target,
        level,
        internal_format,
        width,
        height,
        border,
        pixel_format,
        pixel_type,
        data,
    ):
        self.tex_image_calls.append({
            "texture": self.bound_texture,
            "target": target,
            "level": level,
            "internal_format": internal_format,
            "width": width,
            "height": height,
            "border": border,
            "pixel_format": pixel_format,
            "pixel_type": pixel_type,
            "data": data,
        })

    def glTexSubImage2D(
        self,
        target,
        level,
        x_offset,
        y_offset,
        width,
        height,
        pixel_format,
        pixel_type,
        data,
    ):
        self.tex_sub_image_calls.append({
            "texture": self.bound_texture,
            "target": target,
            "level": level,
            "x_offset": x_offset,
            "y_offset": y_offset,
            "width": width,
            "height": height,
            "pixel_format": pixel_format,
            "pixel_type": pixel_type,
            "data": data,
        })

    def glClear(self, mask):
        self.events.append(("clear", mask))

    def glBegin(self, primitive):
        assert self._draw_vertices is None
        self._draw_vertices = []
        self.events.append(("begin", primitive))

    def glTexCoord2f(self, s, t):
        self._pending_tex_coord = (s, t)

    def glVertex2f(self, x, y):
        assert self._draw_vertices is not None
        assert self._pending_tex_coord is not None
        self._draw_vertices.append((self._pending_tex_coord, (x, y)))

    def glEnd(self):
        self.draws.append({
            "texture": self.bound_texture,
            "vertices": self._draw_vertices,
        })
        self._draw_vertices = None
        self._pending_tex_coord = None
        self.events.append(("end", ))

    def glDeleteTextures(self, textures):
        self.deleted_textures.append(tuple(textures))


class FakeGLFW:

    DECORATED = 1
    RESIZABLE = 2
    AUTO_ICONIFY = 3
    REFRESH_RATE = 4
    FALSE = 0
    KEY_ESCAPE = 256
    PRESS = 1

    def __init__(self, width=8, height=2):
        self.width = width
        self.height = height
        self.window = object()
        self.swap_intervals = []
        self.swap_calls = []
        self.context_calls = []
        self.destroyed_windows = []
        self.terminate_calls = 0

    def init(self):
        return True

    def window_hint(self, *args):
        pass

    def create_window(self, *args):
        return self.window

    def set_window_pos(self, *args):
        pass

    def make_context_current(self, window):
        self.context_calls.append(window)

    def swap_interval(self, interval):
        self.swap_intervals.append(interval)

    def get_framebuffer_size(self, window):
        return self.width, self.height

    def swap_buffers(self, window):
        self.swap_calls.append(window)

    def poll_events(self):
        pass

    def window_should_close(self, window):
        return False

    def get_key(self, window, key):
        return 0

    def destroy_window(self, window):
        self.destroyed_windows.append(window)

    def terminate(self):
        self.terminate_calls += 1


@pytest.fixture
def fake_renderer(monkeypatch):
    gl = FakeGL()
    glfw = FakeGLFW()
    monkeypatch.setattr(paired, "_load_gl_modules", lambda: (glfw, gl))
    engine = paired.PairedPatternEngine(width=8, height=2, fps=60)
    return engine, glfw, gl


def test_paired_renderer_allocates_two_persistent_half_width_textures(fake_renderer):
    engine, glfw, gl = fake_renderer

    assert engine.half_width == 4
    assert (engine.texture_b, engine.texture_a) == (101, 202)
    assert glfw.swap_intervals == [1]
    assert [(call[0], call[1]) for call in gl.events if call[0] == "gen_textures"] == [
        ("gen_textures", 2)
    ]
    assert [
        (call["texture"], call["width"], call["height"], call["data"])
        for call in gl.tex_image_calls
    ] == [(101, 4, 2, None), (202, 4, 2, None)]
    assert ("pixel_store", gl.GL_UNPACK_ALIGNMENT, 1) in gl.events

    expected_parameters = {
        (gl.GL_TEXTURE_MIN_FILTER, gl.GL_NEAREST),
        (gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST),
        (gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE),
        (gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE),
    }
    for texture in (101, 202):
        assert {
            (parameter, value)
            for bound, _, parameter, value in gl.texture_parameter_calls
            if bound == texture
        } == expected_parameters


def test_display_pair_updates_b_then_a_without_reallocation_or_input_mutation(fake_renderer):
    engine, glfw, gl = fake_renderer
    frame_a = np.arange(24, dtype=np.uint8).reshape(2, 4, 3)
    frame_b = np.arange(24, 48, dtype=np.uint8).reshape(2, 4, 3)
    original_a = frame_a.copy()
    original_b = frame_b.copy()
    allocation_count = len(gl.tex_image_calls)

    engine.display_pair(frame_a, frame_b)

    assert len(gl.tex_image_calls) == allocation_count
    assert len(gl.tex_sub_image_calls) == 2
    assert gl.tex_sub_image_calls[0]["texture"] == engine.texture_b
    assert gl.tex_sub_image_calls[0]["data"] is frame_b
    assert gl.tex_sub_image_calls[1]["texture"] == engine.texture_a
    assert gl.tex_sub_image_calls[1]["data"] is frame_a
    assert glfw.swap_calls == [engine.window]
    np.testing.assert_array_equal(frame_a, original_a)
    np.testing.assert_array_equal(frame_b, original_b)


def test_display_pair_draws_b_left_and_a_right_with_independent_horizontal_mirrors(
    fake_renderer,
):
    engine, _, gl = fake_renderer
    frame_a = np.zeros((2, 4, 3), dtype=np.uint8)
    frame_b = np.zeros((2, 4, 3), dtype=np.uint8)

    engine.display_pair(frame_a, frame_b)

    assert gl.draws == [
        {
            "texture": engine.texture_b,
            "vertices": [
                ((1, 0), (0, 0)),
                ((0, 0), (4, 0)),
                ((0, 1), (4, 2)),
                ((1, 1), (0, 2)),
            ],
        },
        {
            "texture": engine.texture_a,
            "vertices": [
                ((1, 0), (4, 0)),
                ((0, 0), (8, 0)),
                ((0, 1), (8, 2)),
                ((1, 1), (4, 2)),
            ],
        },
    ]


def test_display_pair_only_copies_non_contiguous_inputs(fake_renderer, monkeypatch):
    engine, _, gl = fake_renderer
    frame_a = np.zeros((2, 8, 3), dtype=np.uint8)[:, ::2, :]
    frame_b = np.ones((2, 4, 3), dtype=np.uint8)
    assert not frame_a.flags.c_contiguous
    assert frame_b.flags.c_contiguous

    original_ascontiguousarray = np.ascontiguousarray
    copied_inputs = []

    def record_ascontiguousarray(frame):
        copied_inputs.append(frame)
        return original_ascontiguousarray(frame)

    monkeypatch.setattr(paired.np, "ascontiguousarray", record_ascontiguousarray)

    engine.display_pair(frame_a, frame_b)

    assert len(copied_inputs) == 1
    assert copied_inputs[0] is frame_a
    assert gl.tex_sub_image_calls[0]["data"] is frame_b
    assert gl.tex_sub_image_calls[1]["data"].flags.c_contiguous
    np.testing.assert_array_equal(gl.tex_sub_image_calls[1]["data"], frame_a)


@pytest.mark.parametrize(
    ("frame_a", "frame_b", "error", "message"),
    [
        (
            np.zeros((2, 4, 3), dtype=np.float32),
            np.zeros((2, 4, 3), dtype=np.uint8),
            ValueError,
            "frame_a must use dtype uint8",
        ),
        (
            np.zeros((2, 4), dtype=np.uint8),
            np.zeros((2, 4, 3), dtype=np.uint8),
            ValueError,
            "frame_a must have shape HxWx3",
        ),
        (
            np.zeros((2, 5, 3), dtype=np.uint8),
            np.zeros((2, 4, 3), dtype=np.uint8),
            ValueError,
            "frame_a shape",
        ),
        (
            np.zeros((2, 4, 3), dtype=np.uint8),
            np.zeros((3, 4, 3), dtype=np.uint8),
            ValueError,
            "frame_b shape",
        ),
        (
            object(),
            np.zeros((2, 4, 3), dtype=np.uint8),
            TypeError,
            "frame_a must be a numpy array",
        ),
    ],
)
def test_display_pair_rejects_invalid_inputs(
    fake_renderer,
    frame_a,
    frame_b,
    error,
    message,
):
    engine, _, _ = fake_renderer

    with pytest.raises(error, match=message):
        engine.display_pair(frame_a, frame_b)


def test_paired_renderer_rejects_odd_drawable_width_before_glfw_initialization():
    with pytest.raises(ValueError, match="even"):
        paired.PairedPatternEngine(width=7, height=2)


def test_pair_render_coordinator_passes_logical_frames_without_cpu_mirroring(monkeypatch):
    frame_a = np.arange(24, dtype=np.uint8).reshape(2, 4, 3)
    frame_b = np.arange(24, 48, dtype=np.uint8).reshape(2, 4, 3)
    displayed = []

    class FakeEngine:

        def display_pair(self, received_a, received_b):
            displayed.append((received_a, received_b))

    def fail_fliplr(*args, **kwargs):
        raise AssertionError("CPU mirroring must not run in the paired coordinator")

    monkeypatch.setattr(pair_render.np, "fliplr", fail_fliplr)

    pair_render._display_frame_pair(FakeEngine(), paired.FramePair(a=frame_a, b=frame_b))

    assert displayed == [(frame_a, frame_b)]
    assert displayed[0][0] is frame_a
    assert displayed[0][1] is frame_b


def test_stutter_phase_timing_is_rate_limited_and_reports_slowest_phase(
    fake_renderer,
    monkeypatch,
    caplog,
):
    engine, _, _ = fake_renderer
    frame = np.zeros((2, 4, 3), dtype=np.uint8)
    timestamps = iter([
        10.000,
        10.001,
        10.002,
        10.003,
        10.004,
        10.010,
        10.030,
        10.031,
        10.032,
        10.033,
        10.034,
        10.054,
        10.060,
        10.061,
        10.062,
        10.063,
        10.064,
        10.084,
    ])
    monkeypatch.setattr(paired.time, "perf_counter", lambda: next(timestamps))
    caplog.set_level(logging.WARNING, logger="dmdcontrol")

    engine.display_pair(frame, frame)
    engine.display_pair(frame, frame)
    engine.display_pair(frame, frame)

    warnings = [
        record.getMessage()
        for record in caplog.records
        if "Paired render stutter" in record.getMessage()
    ]
    assert len(warnings) == 1
    assert "dt=30.00ms" in warnings[0]
    assert "input=" in warnings[0]
    assert "upload_b=" in warnings[0]
    assert "upload_a=" in warnings[0]
    assert "draw=" in warnings[0]
    assert "swap=20.00ms" in warnings[0]
    assert "total=24.00ms" in warnings[0]
    assert "target=16.67ms" in warnings[0]
    assert "slow_phase=swap" in warnings[0]
    assert engine.dropped_frames == 2


def test_cleanup_deletes_both_textures_while_context_is_current(fake_renderer):
    engine, glfw, gl = fake_renderer

    engine.cleanup()

    assert gl.deleted_textures == [(engine.texture_b, engine.texture_a)]
    assert glfw.context_calls[-1] is engine.window
    assert glfw.destroyed_windows == [engine.window]
    assert glfw.terminate_calls == 1
