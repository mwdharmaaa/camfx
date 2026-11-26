# CamFX

Real-time custom virtual camera studio for Linux featuring OpenGL GLSL shaders, EffecTV filters, Studio REC HUD overlay, live color grading, and `v4l2loopback` virtual webcam output. Packaged into a `.deb` archive following the Commanda installation pipeline.

---

## 1. Key Features

* **24 Real-Time Effects across 4 Categories**:
  * **Color & Cinema**: Normal, Cinema Warm, Cyberpunk Neon, Noir Sin City, Vintage Sepia, Cross Process, Soft Glow, Soft Blur
  * **Retro & Stylize**: Glitch RGB, Retro CRT, Pixel 8-Bit, Old Film 1920s
  * **Art & Vision**: Night Vision, Thermal Heat, X-Ray Negative, Neon Edge, Sketch Outline
  * **Lens & Fun**: Fisheye Lens, Bulge Zoom, Twirl Vortex, Light Tunnel, Mirror Split, Warp Wave, Vertigo Echo
* **Live Controls & Overlay**: Horizontal Mirror, **Scanline Glitch** toggle (switch between raw YUY2 motion tearing and clean MJPEG capture), live Brightness / Contrast / Saturation adjustments, **Studio REC HUD** (viewfinder brackets, live clock, active effect badge), and **Custom Watermark Text**.
* **Photo & Video Capture**: **Take Photo** saves PNG snapshots to `~/Pictures/CamFX/`, and **Record Video** captures MP4/WebM recordings to `~/Videos/CamFX/` (including live effect switches).
* **Virtual Camera (`v4l2loopback`)**: Streams processed video to `/dev/video10` (`CamFX Virtual Camera`) for Chrome, Google Meet, Zoom, Discord, and OBS.
* **Headless CLI Mode**: Run the virtual camera pipeline directly from a terminal or background service without opening the GTK4 GUI.

---

## 2. Installation (Commanda Pipeline Style)

Build, test, package into `.deb`, install system-wide, and configure persistent `v4l2loopback` kernel options:

```bash
./install.sh
```

---

## 3. Usage

* **Desktop Launcher**: Open **CamFX** from your application menu.
* **Terminal CLI**:
  ```bash
  camfx
  camfx --headless --effect cyberpunk --hud --watermark "Live"
  camfx --list-effects
  camfx --list-devices
  camfx --version
  ```
* **Run Directly Without Installing**:
  ```bash
  ./runapp.sh
  ```

---

## 4. Testing & Packaging

```bash
./test.sh
make package
```
