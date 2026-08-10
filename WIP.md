## Major changes
- Everything is now in `config.yaml`. It's loaded with `dmdcontrol/utils/config.py`

## Moved
- `dmdcontrol/patterns/calibration_square.py -> tests/calibration_square.py` - probably will need to be edited though
- `images/ -> tests/images/`
- `notebooks/ -> tests/notebooks/`

## To Do
- put this in main somewhere
```
if target_hz <= 0:
        raise ValueError("target_hz must be positive")

 raise ValueError("dark_time_us must be non-negative")
 if CONFIG.get('frame_utilization', 1.0) <= 0.0 or CONFIG.get('frame_utilization', 1.0) > 1.0:
        raise ValueError("CONFIG.get('frame_utilization', 1.0) must be in the interval (0, 1].")
```