# Scripts

The repository-root `run_*.sh` files are the public launch commands.
This directory holds their implementation details:

- `lib/`: shared shell helpers for wake, config lookup, xinit, NVIDIA/X11 layout setup, and Python module execution.
ex. this would be a command I use

./run_dmd_pair_capture.sh   --test a-kernel-b-static   --kernel-px 63   --exposure-us 6000   --dark-time-us 2000   --runtime-seconds 5   --polarity-mode ignore   --event-noise-filter none   --max-accumulation-triggers 512   --output-root runs/camera   -v
