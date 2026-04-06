# DisplayPort and X11 Video Pipeline Quirks for DMD Bit-Packing

When sending 24 mathematically precise binary bit-planes packed into a single 60Hz RGB888 video frame to the TI DLPC900, the Linux X11 server and GPU drivers will actively attempt to compress, scale, or dither the video signal. This destroys the bit-packing integrity. 

This document details the three major pitfalls we encountered and how the `xinitrc_dmd.sh` wrapper script systematically defeats them.

## 1. Deep Color / 10-bit Scaling (The "Missing Bottom Row" Bug)
**The Symptom:** When displaying the 4x6 Numbered Grid diagnostic, the DMD only displayed the top 3 rows (regions 1-18). The bottom row (regions 19-24) was completely black.
**The Cause:** Modern GPUs support "Deep Color" (10-bit or 12-bit color per channel). Linux detected the DLPC900's DisplayPort EDID and decided to send the 1920x1080 signal using 10-bit depth (`max bpc: 10` or `auto`). Because our OpenGL pipeline generates exactly 8-bit RGB values, the GPU mathematically scaled those 8-bit numbers up to 10-bit before sending them over the wire. This bit-shift pushed the highest 6 bits (the upper bits of the Blue channel) completely off a cliff, destroying regions 19 through 24.
**The Fix:** 
```bash
xrandr --output DP-2 --set "max bpc" 8
```
This strictly limits the DisplayPort pipeline to 8-bit color, preserving the exact 1:1 bit-packing.

## 2. YCbCr 4:2:2 Chroma Subsampling (The "Mixed Colors" Bug)
**The Symptom:** When sending pure colors (Red, Green, Blue) or the Numbered Grid, the channels bleed into each other, creating blurry artifacts or mixing bits between regions.
**The Cause:** When a GPU sees a standard `1920x1080@60Hz` timing, it assumes a standard consumer TV is plugged in. To save DisplayPort bandwidth, it quietly switches from raw RGB to YCbCr 4:2:2 or 4:2:0 compressed video. It compresses the Red and Blue channels (Cb and Cr) while leaving Green (Luma) mostly intact.
**The Fix:** We cannot rely on driver flags alone. We must defeat the GPU's "Standard TV Detection" by providing a custom, non-standard CVT-R modeline with a slightly shifted pixel clock.
```bash
# Shifted pixel clock from 138.50 MHz to 138.51 MHz
xrandr --newmode "1920x1080_60_RAW" 138.51 1920 1968 2000 2080 1080 1083 1088 1111 +hsync -vsync
```
Because this modeline doesn't match the GPU's internal TV database, it falls back to streaming uncompressed raw PC RGB data.

## 3. Temporal Dithering / FRC (The "Flashing" Bug)
**The Symptom:** Static grayscale patterns (like a checkerboard) look fine, but colored patterns flash randomly or exhibit static noise.
**The Cause:** The GPU driver (especially Nouveau or AMD) applies Frame Rate Control (FRC) or spatial dithering to smooth out color gradients. This rapidly flashes pixels between two colors, scrambling the binary data on the wire.
**The Fix:** Forcefully disable dithering properties in `xrandr`. Note that many drivers reset these properties to "auto" immediately after a modeline change, so they must be applied *twice*: once before the mode switch, and once immediately after.
```bash
xrandr --output DP-2 --set "dithering mode" "off"
xrandr --output DP-2 --set "dithering depth" "8 bpc"
xrandr --output DP-2 --set "Broadcast RGB" "Full"
xrandr --output DP-2 --set "color range" "Full"
xrandr --output DP-2 --set "dither" "off"
```

## 4. Visualizing the Temporal Display (The "3-Part Flashing" Illusion)
When you pack 24 bit-planes into an RGB image, the DLPC900 does not display all the colors simultaneously. In Video Pattern Mode, it extracts them sequentially:
1. It flashes the 8 bits of the **Green** channel for ~5.5ms.
2. It flashes the 8 bits of the **Red** channel for ~5.5ms.
3. It flashes the 8 bits of the **Blue** channel for ~5.5ms.

If a diagnostic pattern uses different colors for different physical areas of the screen (like the Gradient or Numbered Grid), the DMD will physically illuminate the Left side of the screen, then the Middle, then the Right in a high-speed 1440 Hz sequence. To the human eye, this creates a bizarre flashing/dithering optical illusion because it forms a beat frequency with your vision. 

**This is entirely normal.** A high-speed camera synchronized to the `TRIG_OUT_2` hardware pulse will capture each of the 24 discrete binary frames perfectly.