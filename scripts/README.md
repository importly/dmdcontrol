# Scripts

The repository-root `run_*.sh` files are the public hardware launch commands.
This directory holds their implementation details:

- `lib/`: shared shell helpers for wake, config lookup, xinit, and Python module execution.
- `xinit/`: X session wrappers that configure NVIDIA/X11 before launching `dmdcontrol`.
- `debug/`: deprecated or USB-only helper scripts kept out of the top-level command set.
