import json
from pathlib import Path


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
    return "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
    )


def test_timing_sweep_notebooks_exist_and_are_parseable():
    expected = {
        "01_generate_timing_sweep_commands.ipynb": [
            "SWEEP_MANIFEST_PATH",
            "SWEEP_COMMAND_PATH",
            "dark_time_us_values",
            "trigger_delay_fraction_values",
            "run_camera_sync_sweep.sh",
            "number_size_px",
            "b_dot_radius",
            "numbers_exposure_us_values",
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
