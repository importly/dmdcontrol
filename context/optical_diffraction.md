# Optical Diffraction and Gray Bands on 1x1 DMD Checkerboards

When operating the DMD with a **1x1 single-pixel checkerboard** (where every adjacent mirror alternates between the ON and OFF states) and illuminating it with coherent laser light, you may observe "gray bands," Moiré fringes, or a severe loss of contrast instead of a uniform gray output.

This is a well-documented optical phenomenon and **is not a software or pixel-mapping bug.**

## The Physics of DMD Diffraction
A DMD is an array of highly reflective aluminum micromirrors arranged on a tight pitch (7.6 µm for the DLP6500). 
When illuminated by a highly coherent source like a laser, the DMD physically acts as a **2D Blazed Diffraction Grating**.

### Why the 1x1 Checkerboard behaves uniquely:
1. **High-Frequency Grating:** A 1x1 checkerboard creates the absolute highest spatial frequency possible on the DMD array. 
2. **Diffraction Orders:** Light scattering off this 1x1 periodic structure splits into widely separated, discrete diffraction orders. 
3. **Aperture Clipping:** Because the diffraction angle is so steep for a 1-pixel period, many of the diffracted light rays (higher orders) completely miss the collection aperture of your projection lens. 
4. **Interference:** The orders that *do* make it through the lens interfere with one another, causing macroscopic interference fringes or "gray bands" across the projected image.

### How to verify 1:1 Pixel Mapping (Software vs. Optical)
To mathematically prove that the software and GPU are sending a perfect 1:1 mapped image without scaling, you can change the spatial frequency:

1. Display a **2x2 pixel checkerboard** (`--test-2x2`).
2. Display alternating **1-pixel vertical lines** (`--test-lines`).

If the gray bands drastically change shape, frequency, or disappear entirely when you switch to a 2x2 or line pattern, it definitively proves the bands are an **optical diffraction artifact** caused by the 1x1 grating pitch, rather than an OS/GPU scaling issue. 

If the GPU or X11 were mathematically blurring or scaling the image, all high-frequency patterns (1x1, 2x2, lines) would suffer from uniform smearing/blurring, not discrete interference bands.

*Note: If you ever need to use a 1x1 checkerboard with a laser in production, you must carefully calculate the diffraction angles based on your laser's wavelength (λ) and the mirror pitch (d), and ensure your collection optics have a sufficiently high Numerical Aperture (NA) to capture the necessary diffraction orders.*