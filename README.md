# CamFX

Aplikasi kamera virtual dengan efek khusus real-time (GLSL OpenGL shaders, EffecTV, Studio REC HUD, color grading, dan virtual camera `v4l2loopback`) untuk Linux, dikemas dalam paket `.deb` dengan pola instalasi seperti **Commanda**.

## Fitur Utama
- **24 Efek Real-Time** dalam 4 kategori:
  - **Color & Cinema:** Normal, Cinema Warm, Cyberpunk Neon, Noir Sin City, Vintage Sepia, Cross Process, Soft Glow, Soft Blur
  - **Retro & Stylize:** Glitch RGB, Retro CRT, Pixel 8-Bit, Old Film 1920s
  - **Art & Vision:** Night Vision, Thermal Heat, X-Ray Negative, Neon Edge, Sketch Outline
  - **Lens & Fun:** Fisheye Lens, Bulge Zoom, Twirl Vortex, Light Tunnel, Mirror Split, Warp Wave, Vertigo Echo
- **Controls & Overlay Live:** Mirror Horizontal, Brightness / Contrast / Saturation, **Studio REC HUD** (viewfinder + jam + badge efek aktif), dan **Custom Watermark Text**.
- **Snapshot:** Simpan hasil kamera ber-efek ke `~/Pictures/CamFX/`.
- **Virtual Camera (`v4l2loopback`):** Mengirim output ke `/dev/video10` (`CamFX Virtual Camera`) agar terbaca oleh Chrome, Google Meet, Zoom, Discord, dan OBS.
- **Mode Headless CLI:** Jalankan kamera virtual di terminal/background tanpa membuka GUI.

## Cara Pasang (Seperti Commanda)
```bash
./install.sh
```

## Cara Menjalankan
- Dari menu aplikasi: cari **CamFX**
- Dari terminal:
  ```bash
  camfx
  camfx --headless --effect cyberpunk --hud --watermark "Live"
  camfx --list-effects
  camfx --list-devices
  camfx --version
  ```
- Atau jalankan langsung tanpa install sistem:
  ```bash
  ./runapp.sh
  ```
