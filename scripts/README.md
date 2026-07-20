# Scripts

The repository-root `run_*.sh` files are the public launch commands.
This directory holds their implementation details:

- `dmd_shell_common.sh`: shared wake, config lookup, xinit, and Python module execution helpers.
- `dmd_x11_common.sh`: NVIDIA/X11 layout setup helpers.
- `dmd_xinit_client.sh`: pair-only xinit client used by all hardware launchers.
ex. this would be a command I use

./run_dmd_pair_capture.sh   --test a-kernel-b-static   --kernel-px 63   --exposure-us 6000   --dark-time-us 2000   --runtime-seconds 5   --polarity-mode ignore   --event-noise-filter none   --max-accumulation-triggers 512   --output-root runs/camera   -v
