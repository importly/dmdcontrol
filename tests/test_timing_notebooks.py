import json
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


def test_timing_sweep_notebooks_exist_and_are_parseable():
    expected = {
        "01_generate_timing_sweep_commands.ipynb": [
            "SWEEP_MANIFEST_PATH",
            "SWEEP_COMMAND_PATH",
            "dark_time_us_values",
            "trigger_rising_delay_us_values",
            "run_camera_sync_sweep.sh",
            "number_size_px",
            "b_dot_radius",
            "exposure_us_values",
            "sync_check_argv",
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
    assert "./run_camera_sync_check.sh" not in generator_source
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
        ["shape_label_for_frame", "shape_template_label_map", "shape_overlap_scores"],
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
