import json
import re
from types import SimpleNamespace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = ROOT / "notebooks"


def _load_notebook(name):
    path = NOTEBOOKS / name
    assert path.exists(), f"missing notebook: {path}"
    with path.open(encoding="utf-8") as handle:
        notebook = json.load(handle)
    assert notebook["nbformat"] == 4
    assert notebook["cells"]
    return notebook


def _joined_source(notebook):
    return "\n".join("".join(cell.get("source", [])) for cell in notebook["cells"])


def _exec_notebook_functions(notebook, function_names):
    source = _joined_source(notebook)
    namespace = {"np": np}
    for name in function_names:
        marker = f"def {name}("
        start = source.find(marker)
        assert start >= 0, f"{name!r} missing from notebook"
        next_def = source.find("\ndef ", start + len(marker))
        next_cell = source.find("\n# %%", start + len(marker))
        candidates = [value for value in (next_def, next_cell) if value >= 0]
        end = min(candidates) if candidates else len(source)
        exec(source[start:end], namespace)
    return namespace


def _notebook_cell_source_containing(notebook, required_text):
    for cell in notebook["cells"]:
        source = "".join(cell.get("source", []))
        if required_text in source:
            return source
    raise AssertionError(f"{required_text!r} missing from notebook")


def _exec_trim_cell_tail_without_resolution_global(notebook):
    source = _notebook_cell_source_containing(notebook, "def write_trimmed_display_aedat4(")
    prefix, tail = source.split("\ntrim_cycles =", 1)
    tail = "trim_cycles =" + tail
    captured = {}

    def fake_process_accumulation_triggers(*args, **kwargs):
        trigger_count = int(kwargs["max_accumulation_triggers"])
        return SimpleNamespace(
            final=[
                {"timestamp": 1000 + index * 1000, "edge": "rising"}
                for index in range(trigger_count)
            ]
        )

    def fake_write_trimmed_display_aedat4(
        output_path,
        metadata_path,
        arrays,
        selected_triggers,
        resolution,
        source_aedat4_path,
        buffer_us=2000,
    ):
        captured["output_path"] = str(output_path)
        captured["metadata_path"] = str(metadata_path)
        captured["resolution"] = resolution
        captured["selected_trigger_count"] = len(selected_triggers)
        return {
            "resolution": [int(resolution[0]), int(resolution[1])],
            "selected_trigger_count": len(selected_triggers),
            "buffer_us": int(buffer_us),
        }

    namespace = {
        "AEDAT4_PATH": ROOT / "raw.aedat4",
        "RUN_DIR": ROOT,
        "STATIC_RAINBOW_FRAME_COUNT": 30,
        "Path": Path,
        "ceil": __import__("math").ceil,
        "cycle_length": 120,
        "default_cycles": 1,
        "default_offset_us": 0,
        "default_window_us": 8000,
        "event_arrays": {
            "t": np.array([1000, 2000], dtype=np.int64),
            "x": np.array([1, 2], dtype=np.int64),
            "y": np.array([3, 4], dtype=np.int64),
            "p": np.array([True, False], dtype=np.bool_),
        },
        "json": json,
        "np": np,
        "recording": SimpleNamespace(triggers=[]),
        "startup_leader_trigger_count": 0,
        "width": 640,
        "height": 480,
    }
    exec(prefix, namespace)
    namespace["_process_accumulation_triggers"] = fake_process_accumulation_triggers
    namespace["write_trimmed_display_aedat4"] = fake_write_trimmed_display_aedat4
    exec(tail, namespace)
    return captured


def test_timing_sweep_notebooks_exist_and_are_parseable():
    expected = {
        "01_generate_timing_sweep_commands.ipynb": [
            "SWEEP_MANIFEST_PATH",
            "SWEEP_COMMAND_PATH",
            "dark_time_us_values",
            "trigger_rising_delay_us_values",
            "run_camera_sync_check.sh",
            "number_size_px",
            "b_dot_radius",
            "exposure_us_values",
            "sync_check_argv",
            "--name-override",
            "Each row runs an ordinary sync-check command",
        ],
        "02_analyze_timing_sweep_results.ipynb": [
            "summary.json",
            "events_per_accumulation_window",
            "number_sequence",
            "expected_number",
            "crossover_score",
            "timing_score",
            "ranked_runs",
        ],
        "03_accumulation_offset_rescan.ipynb": [
            "filtered_events.npz",
            "offset_us_values",
            "rescan_offsets",
            "best_offset_by_run",
        ],
    }

    for name, required_terms in expected.items():
        notebook = _load_notebook(name)
        source = _joined_source(notebook)
        for term in required_terms:
            assert term in source, f"{term!r} missing from {name}"

    generator_source = _joined_source(_load_notebook("01_generate_timing_sweep_commands.ipynb"))
    assert "./run_camera_sync_sweep.sh" not in generator_source
    assert "run_dmd_pair_capture.sh" not in generator_source
    assert "kernel_exposure_us" not in generator_source
    assert "numbers_exposure_us" not in generator_source
    assert "count_exposure_us" not in generator_source


def test_laser3_notebook_repeats_rainbow_phase_per_number_cycle():
    notebook = _load_notebook("07_fast_accumulation_offset_explorer_laser3.ipynb")
    source = _joined_source(notebook)
    namespace = _exec_notebook_functions(
        notebook,
        ["rainbow_color_segment_for_slot", "rainbow_cycle_phase", "rainbow_phase_color"],
    )

    rainbow_cycle_phase = namespace["rainbow_cycle_phase"]
    rainbow_phase_color = namespace["rainbow_phase_color"]

    phases = [rainbow_cycle_phase(frame_index, cycle_length=3) for frame_index in range(10)]

    assert phases[:3] == phases[3:6]
    assert phases[:3] == phases[6:9]
    assert phases[0] == phases[9]
    assert len(set(phases[:3])) == 3

    cycle_colors = [rainbow_phase_color(phase) for phase in phases[:3]]

    assert len(set(cycle_colors)) == 3
    assert cycle_colors == [rainbow_phase_color(phase) for phase in phases[3:6]]
    assert rainbow_phase_color(0.0) == (255, 0, 0)
    assert rainbow_phase_color(1 / 3) == (0, 255, 0)
    assert rainbow_phase_color(2 / 3) == (0, 0, 255)
    assert rainbow_phase_color(rainbow_cycle_phase(0, cycle_length=3, labels=[2, 3, 1])) == (0, 255, 0)
    assert rainbow_phase_color(rainbow_cycle_phase(1, cycle_length=3, labels=[2, 3, 1])) == (0, 0, 255)
    assert rainbow_phase_color(rainbow_cycle_phase(2, cycle_length=3, labels=[2, 3, 1])) == (255, 0, 0)
    assert "render_rainbow_provenance_sheet" in source
    assert "rainbow_frame_slider" in source


def test_laser3_notebook_separates_display_sequence_from_analysis_phase():
    notebook = _load_notebook("07_fast_accumulation_offset_explorer_laser3.ipynb")
    namespace = _exec_notebook_functions(
        notebook,
        [
            "analysis_label_for_frame",
            "frame_title_label_for_frame",
            "legend_labels_for_analysis_phase",
            "rainbow_color_segment_for_slot",
        ],
    )

    display_sequence = [2, 3, 1]
    raw_labels = [
        namespace["analysis_label_for_frame"](
            index,
            labels=display_sequence,
            cycle_length=3,
            label_phase_shift=0,
        )
        for index in range(3)
    ]
    shifted_labels = [
        namespace["analysis_label_for_frame"](
            index,
            labels=display_sequence,
            cycle_length=3,
            label_phase_shift=1,
        )
        for index in range(6)
    ]
    legend_labels = namespace["legend_labels_for_analysis_phase"](
        labels=display_sequence,
        cycle_length=3,
        label_phase_shift=1,
    )

    assert raw_labels == [2, 3, 1]
    assert shifted_labels == [1, 2, 3, 1, 2, 3]
    assert legend_labels == [
        {"slot": 0, "label": 1, "segment": 1},
        {"slot": 1, "label": 2, "segment": 2},
        {"slot": 2, "label": 3, "segment": 0},
    ]
    assert [
        namespace["rainbow_color_segment_for_slot"](item["slot"], 3, labels=display_sequence)
        for item in legend_labels
    ] == [1, 2, 0]
    assert "DEFAULT_RAINBOW_LABEL_PHASE_SHIFT = int(globals().get(\"RAINBOW_LABEL_PHASE_SHIFT\", 1" in _joined_source(notebook)

    title_pairs = []
    for index in range(3, 6):
        raw_label = display_sequence[index % 3]
        analysis_label = namespace["frame_title_label_for_frame"](
            index,
            labels=display_sequence,
            cycle_length=3,
            label_phase_shift=1,
        )
        title_pairs.append((analysis_label, raw_label))
    assert title_pairs == [(1, 2), (2, 3), (3, 1)]


def test_laser3_notebook_counts_temporal_provenance_buckets():
    notebook = _load_notebook("07_fast_accumulation_offset_explorer_laser3.ipynb")
    namespace = _exec_notebook_functions(notebook, ["event_provenance_counts_for_frame"])

    trigger_ts = np.array([0, 5000, 10000, 15000], dtype=np.int64)
    event_ts = np.array(
        [
            4800,  # outside the accumulation window, before the previous-trigger tail
            4900,  # selected pre-trigger event from previous phase
            5050,  # selected current-phase event
            8849,  # selected current-phase event near accumulation end
            8900,  # post-window diagnostic event
            10020,  # next-phase diagnostic event
        ],
        dtype=np.int64,
    )

    counts = namespace["event_provenance_counts_for_frame"](
        frame_index=1,
        event_ts=event_ts,
        trigger_ts=trigger_ts,
        offset_us=-150,
        window_us=4000,
        post_window_us=1500,
    )

    assert counts["window_start_us"] == 4850
    assert counts["window_stop_us"] == 8850
    assert counts["selected_events"] == 3
    assert counts["pre_trigger_events"] == 1
    assert counts["in_window_events"] == 2
    assert counts["post_window_events"] == 1
    assert counts["previous_phase_events"] == 1
    assert counts["current_phase_events"] == 3
    assert counts["next_phase_events"] == 1


def test_laser3_notebook_computes_trimmed_aedat4_time_window():
    notebook = _load_notebook("07_fast_accumulation_offset_explorer_laser3.ipynb")
    namespace = _exec_notebook_functions(
        notebook,
        ["displayed_trigger_trim_window", "trim_event_arrays_for_time_window"],
    )

    trigger_ts = np.array([1000, 6000, 11000, 16000], dtype=np.int64)
    window = namespace["displayed_trigger_trim_window"](
        trigger_ts,
        frame_count=3,
        buffer_us=2000,
    )

    assert window == {
        "start_us": -1000,
        "stop_us": 13000,
        "first_trigger_us": 1000,
        "last_trigger_us": 11000,
        "selected_trigger_count": 3,
        "buffer_us": 2000,
    }

    arrays = {
        "t": np.array([0, 999, 1000, 12999, 13000], dtype=np.int64),
        "x": np.array([1, 2, 3, 4, 5], dtype=np.int64),
        "y": np.array([6, 7, 8, 9, 10], dtype=np.int64),
        "p": np.array([True, False, True, False, True], dtype=np.bool_),
    }
    trimmed = namespace["trim_event_arrays_for_time_window"](arrays, window)

    assert trimmed["t"].tolist() == [0, 999, 1000, 12999]
    assert trimmed["x"].tolist() == [1, 2, 3, 4]
    assert trimmed["y"].tolist() == [6, 7, 8, 9]
    assert trimmed["p"].tolist() == [True, False, True, False]


def test_laser3_notebook_writes_trimmed_display_aedat4_artifact():
    notebook = _load_notebook("07_fast_accumulation_offset_explorer_laser3.ipynb")
    source = _joined_source(notebook)

    assert "TRIMMED_AEDAT4_TRIGGER_COUNT = STATIC_RAINBOW_FRAME_COUNT" in source
    assert "TRIMMED_AEDAT4_BUFFER_US = 2000" in source
    assert "trimmed_displayed_30_triggers_plus_2000us.aedat4" in source
    assert "write_trimmed_display_aedat4(" in source
    assert "addEventStream" in source
    assert "addTriggerStream" in source
    assert "writeEvents" in source
    assert "writeTriggerPacket" in source


def test_count_offset_notebook_writes_trimmed_display_aedat4_artifact():
    notebook = _load_notebook("07_fast_accumulation_offset_explorer_count_20260629_174138.ipynb")
    source = _joined_source(notebook)
    namespace = _exec_notebook_functions(
        notebook,
        ["displayed_trigger_trim_window", "trim_event_arrays_for_time_window"],
    )

    trigger_ts = np.array([10_000, 20_000, 30_000, 40_000], dtype=np.int64)
    window = namespace["displayed_trigger_trim_window"](
        trigger_ts,
        frame_count=3,
        buffer_us=2000,
    )

    assert window == {
        "start_us": 8000,
        "stop_us": 32000,
        "first_trigger_us": 10000,
        "last_trigger_us": 30000,
        "selected_trigger_count": 3,
        "buffer_us": 2000,
    }

    arrays = {
        "t": np.array([7999, 8000, 10000, 31999, 32000], dtype=np.int64),
        "x": np.array([1, 2, 3, 4, 5], dtype=np.int64),
        "y": np.array([6, 7, 8, 9, 10], dtype=np.int64),
        "p": np.array([True, False, True, False, True], dtype=np.bool_),
    }
    trimmed = namespace["trim_event_arrays_for_time_window"](arrays, window)

    assert trimmed["t"].tolist() == [8000, 10000, 31999]
    assert trimmed["x"].tolist() == [2, 3, 4]
    assert trimmed["y"].tolist() == [7, 8, 9]
    assert trimmed["p"].tolist() == [False, True, False]
    assert "TRIMMED_AEDAT4_TRIGGER_COUNT = max(1, int(default_cycles) * int(cycle_length))" in source
    assert "TRIMMED_AEDAT4_BUFFER_US = 2000" in source
    assert "trimmed_displayed_{TRIMMED_AEDAT4_TRIGGER_COUNT}_triggers_plus_{TRIMMED_AEDAT4_BUFFER_US}us.aedat4" in source
    assert "write_trimmed_display_aedat4(" in source
    assert "addEventStream" in source
    assert "addTriggerStream" in source
    assert "writeEvents" in source
    assert "writeTriggerPacket" in source


def test_recent_accumulation_notebooks_skip_startup_leader_triggers():
    notebook_names = [
        "07_fast_accumulation_offset_explorer_count_20260629_160740.ipynb",
        "07_fast_accumulation_offset_explorer_count_20260629_174138.ipynb",
        "07_fast_accumulation_offset_explorer_count_startup_leader_20260701.ipynb",
        "07_fast_accumulation_offset_explorer_laser3.ipynb",
    ]

    for notebook_name in notebook_names:
        source = _joined_source(_load_notebook(notebook_name))

        assert "startup_leader.trigger_count" in source, notebook_name
        assert "startup_leader_trigger_count" in source, notebook_name
        assert "startup_leader_trigger_count=startup_leader_trigger_count" in source, notebook_name


def test_trim_cells_use_defined_recording_resolution_and_displayed_frame_count():
    expected_counts = {
        "07_fast_accumulation_offset_explorer_laser3.ipynb": 30,
        "07_fast_accumulation_offset_explorer_count_20260629_174138.ipynb": 120,
    }

    for notebook_name, expected_count in expected_counts.items():
        notebook = _load_notebook(notebook_name)
        captured = _exec_trim_cell_tail_without_resolution_global(notebook)

        assert captured["resolution"] == (640, 480), notebook_name
        assert captured["selected_trigger_count"] == expected_count, notebook_name
        assert f"trimmed_displayed_{expected_count}_triggers_plus_2000us.aedat4" in captured["output_path"], notebook_name
        assert f"trimmed_displayed_{expected_count}_triggers_plus_2000us.json" in captured["metadata_path"], notebook_name


def test_laser3_notebook_uses_readable_rainbow_view_defaults():
    notebook = _load_notebook("07_fast_accumulation_offset_explorer_laser3.ipynb")
    source = _joined_source(notebook)

    assert "RAINBOW_FONT" in source
    assert "truetype(\"DejaVuSans.ttf\", 24)" in source
    assert "rainbow_dense_roi" in source
    assert 'rainbow_crop_dropdown = widgets.Dropdown(value="auto"' in source
    assert "rainbow_pad_slider = widgets.IntSlider(value=12" in source
    assert "dot_size: int = 1" in source
    assert "rainbow_dot_slider = widgets.IntSlider(value=1" in source
    assert "rainbow_tile_scale_slider = widgets.IntSlider(value=3" in source
    assert "rainbow_focus_scale_slider = widgets.IntSlider(value=6" in source
    assert "DEFAULT_RAINBOW_LABEL_PHASE_SHIFT" in source
    assert "rainbow_phase_shift_slider = widgets.IntSlider" in source
    assert "pre_trigger_events" in source
    assert "next_phase_events" in source


def test_laser3_rainbow_header_keeps_analysis_legend_above_focus():
    notebook = _load_notebook("07_fast_accumulation_offset_explorer_laser3.ipynb")
    source = _joined_source(notebook)
    render_block_match = re.search(
        r"def render_rainbow_provenance_sheet\(.*?\ndef render_shape_leakage_sheet\(",
        source,
        re.S,
    )
    assert render_block_match is not None
    render_block = render_block_match.group(0)
    layout = re.search(
        r"header_h = (?P<header>\d+).*?"
        r"draw_rainbow_cycle_legend\(draw, 10, (?P<y>\d+), min\(420, canvas_w - 30\), (?P<height>\d+), "
        r"label_phase_shift=int\(label_phase_shift\)\)",
        render_block,
        re.S,
    )
    assert layout is not None

    header_h = int(layout.group("header"))
    legend_y = int(layout.group("y"))
    legend_height = int(layout.group("height"))
    shifted_label_bottom = legend_y + legend_height + 29 + 24

    assert header_h >= shifted_label_bottom


def test_laser3_notebook_uses_aedat4_triggers_instead_of_trigger_csv():
    notebook = _load_notebook("07_fast_accumulation_offset_explorer_laser3.ipynb")
    source = _joined_source(notebook)

    assert "FORCE_AEDAT4_TRIGGERS = True" in source
    assert 'trigger_source = "raw AEDAT4 rising triggers"' in source
    assert "_process_accumulation_triggers(" in source
    assert "csv_triggers = load_trigger_csv(TRIGGERS_CSV_PATH)" not in source
    assert "selected = csv_triggers" not in source
    assert "if csv_triggers" not in source


def test_laser3_shape_leakage_scores_detect_off_label_structure():
    notebook = _load_notebook("07_fast_accumulation_offset_explorer_laser3.ipynb")
    source = _joined_source(notebook)
    namespace = _exec_notebook_functions(
        notebook,
        [
            "analysis_label_for_frame",
            "shape_label_for_frame",
            "shape_template_label_map",
            "shape_overlap_scores",
        ],
    )

    frames = np.zeros((6, 6, 6), dtype=np.float32)
    frames[0, 0:2, 0:2] = 5.0
    frames[3, 0:2, 0:2] = 4.0
    frames[1, 2:4, 2:4] = 5.0
    frames[4, 2:4, 2:4] = 4.0
    frames[2, 4:6, 4:6] = 5.0
    frames[5, 4:6, 4:6] = 4.0

    label_map, templates = namespace["shape_template_label_map"](
        frames,
        labels=[2, 3, 1],
        cycle_length=3,
        mask_percentile=10.0,
    )
    mixed_frame = np.zeros((6, 6), dtype=np.float32)
    mixed_frame[0:2, 0:2] = 10.0
    mixed_frame[4:6, 4:6] = 5.0
    scores = namespace["shape_overlap_scores"](mixed_frame, label_map, labels=[1, 2, 3])

    assert namespace["shape_label_for_frame"](0, labels=[2, 3, 1], cycle_length=3) == 2
    assert set(templates) == {1, 2, 3}
    assert scores[2] > scores[1] > scores[3]
    assert round(scores[2], 2) == 0.67
    assert round(scores[1], 2) == 0.33
    assert "render_shape_leakage_sheet" in source
    assert 'rainbow_view_dropdown = widgets.Dropdown(value="timestamp"' in source


def test_laser3_notebook_defaults_to_widgets_with_static_png_fallback():
    notebook = _load_notebook("07_fast_accumulation_offset_explorer_laser3.ipynb")
    source = _joined_source(notebook)

    assert 'STATIC_RAINBOW_VIEW = globals().get("STATIC_RAINBOW_VIEW", "shape")' in source
    assert "DEFAULT_RAINBOW_FRAME_COUNT = max(1, min(30, int(available_cycles) * int(cycle_length)))" in source
    assert "value=max(1, min(STATIC_RAINBOW_FRAME_COUNT, int(available_cycles) * int(cycle_length)))" in source
    assert 'ENABLE_INTERACTIVE_WIDGETS = bool(globals().get("ENABLE_INTERACTIVE_WIDGETS", True))' in source
    assert "def render_static_rainbow_diagnostic(" in source
    assert source.count("if HAVE_WIDGETS and ENABLE_INTERACTIVE_WIDGETS:") >= 3
    assert "render_static_rainbow_diagnostic(" in source
    assert "render_fast_sheet(offset_us=default_offset_us)" in source
    assert "render_trigger_timeline(offset_us=default_offset_us)" in source


def test_laser3_notebook_does_not_persist_dead_widget_state():
    notebook = _load_notebook("07_fast_accumulation_offset_explorer_laser3.ipynb")

    assert "widgets" not in notebook.get("metadata", {})
    for cell in notebook["cells"]:
        source = "".join(cell.get("source", []))
        if "if HAVE_WIDGETS and ENABLE_INTERACTIVE_WIDGETS:" in source:
            assert cell.get("outputs", []) == []
            assert cell.get("execution_count") is None


def test_laser3_notebook_exposes_full_trigger_phase_scan():
    notebook = _load_notebook("07_fast_accumulation_offset_explorer_laser3.ipynb")
    source = _joined_source(notebook)

    assert "trigger_period_us = int(default_window_us + default_dark_time_us)" in source
    assert "offset_min_us = -int(trigger_period_us + 1000)" in source
    assert "offset_max_us = int(trigger_period_us + 1000)" in source
    assert "def phase_candidate_metrics(" in source
    assert "def run_phase_offset_scan(" in source
    assert "label_phase_shift" in source
    assert "dark_tail_penalty" in source
    assert "range(-int(trigger_period_us + 1000), int(trigger_period_us + 1000) + 1, 250)" in source


def test_laser3_notebook_defaults_to_pre_trigger_exposure_window():
    notebook = _load_notebook("07_fast_accumulation_offset_explorer_laser3.ipynb")
    source = _joined_source(notebook)

    assert "metadata_offset_us = metadata.get(\"accumulation_start_offset_us\")" in source
    assert "default_offset_us = -int(default_window_us + default_dark_time_us)" in source
    assert "default_window_us = int(" in source
    assert "trigger_period_us = int(default_window_us + default_dark_time_us)" in source
