# DLPC900 Hardware Triggers & Synchronization

## The Secret to 24 Triggers Per Frame (Hardware Supported!)
To synchronize a high-speed camera with the laser bouncing off the DMD at the bit-plane level (24 triggers per 1/60th of a second), **you do not need to abandon the high-speed DisplayPort video stream.**

According to the **DLPU018J Programmer's Guide (Section 2.4.4.1.2 and Table 2-143)**, the DLPC900 has two dedicated hardware trigger outputs:
1. **TRIG_OUT_1**: Typically pulses once at the start of the entire video frame.
2. **TRIG_OUT_2**: Pulses at the start of **every single pattern (bit-plane)** in the LUT sequence.

By default, when we build the Pattern LUT for Video Pattern Mode, `TRIG_OUT_2` is enabled for every entry. This means the DLPC900 will physically fire a hardware electrical pulse 24 times per frame (at 1440 Hz) exactly when each bit-plane physically settles on the micromirrors. This is the absolute best way to sync a high-speed camera because it has sub-microsecond precision and is directly tied to the silicon mirror physics, not software delays.

---

## Software Trigger Approaches

Even with the hardware emitting 24 pulses per frame, you still need a way to tell the system *when* to start the sequence or *what* to display. Here is how the two approaches work:

### Approach A: Video-Simulated Trigger (The Recommended Path)
In **Video Pattern Mode (0x02)**, the DLPC900 is locked to the 60Hz/120Hz DisplayPort VSYNC. It essentially operates like a normal monitor. 
- **How it works:** We keep the OpenGL window running continuously, but we render a completely **black** frame (all zeros). Because the frame is black, the laser reflects away from the target (or is absorbed by the optical dump). When the Python code calls `trigger()`, we immediately swap the OpenGL buffer to the desired pattern. The GPU sends it over DisplayPort, the DLPC900 receives it on the next VSYNC, flashes the 24 bit-planes, and fires `TRIG_OUT_2` 24 times to the camera.
- **Pros:** Extremely fast to update (we can stream complex dynamic patterns in real-time). Doesn't require abandoning the robust video pipeline. 
- **Cons:** The actual physical manifestation of the light is quantized to the next VSYNC interval (up to 16.6ms delay at 60Hz, or 8.3ms at 120Hz).

### Approach B: True Hardware Software-Trigger (Pre-Stored Pattern Mode)
If you cannot tolerate the up to 16.6ms VSYNC delay and need the pattern to fire the *instant* the Python script calls `trigger()`, we must switch to **Pre-Stored Pattern Mode (0x04)** or **Pattern On-The-Fly Mode (0x03)**.
- **How it works:** We stop the DisplayPort stream. We upload the binary patterns over the USB cable directly into the DLPC900's RAM. We configure the hardware to listen for a software command (Trigger Mode = 2). When `trigger()` is called, we send USB Command `0x1A24 = 0x03` (Software Pattern Trigger). The DLPC900 immediately flashes the sequence and fires the 24 `TRIG_OUT_2` pulses.
- **Pros:** Zero VSYNC delay. Completely deterministic firing.
- **Cons:** Uploading images over USB is massively slower than sending them over DisplayPort. It is only viable if projecting a static set of pre-calculated images, rather than dynamically generating them on-the-fly.

## Current Project Direction
We are currently pursuing **Approach A (Video-Simulated Trigger)**, as it allows us to utilize the high-bandwidth DisplayPort pipeline and OpenGL's fast pattern generation, while still producing 24 hardware-accurate pulses per frame via `TRIG_OUT_2`.