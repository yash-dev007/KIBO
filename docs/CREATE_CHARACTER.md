# Creating a New Character for KIBO

This guide covers the complete asset pipeline for adding a new character skin — from design through to a working in-app pet.

---

## How the Engine Resolves Animations

KIBO supports two animation formats. **WebM takes priority; PNG is the automatic fallback.**

| Format | Path Convention |
|--------|----------------|
| WebM | `assets/animations/{skin}/{category}/{clip}.webm` |
| PNG sequence | `assets/animations/{skin}_{category}_{clip}/frame_0001.png` |

You can ship one or both formats per clip — the engine picks WebM first and falls back to PNG transparently.

---

## Step 1 — Choose a Skin Name

Pick a lowercase alphanumeric slug (hyphens and underscores allowed), e.g. `neon`.

Activate it in `config.json`:
```json
"buddy_skin": "neon"
```

This slug becomes the prefix for every asset folder and file the engine looks up.

---

## Step 2 — Required Animations

These map 1:1 to brain states. Missing clips fall back to `idle/stand` silently — the pet won't crash, but the state will look wrong.

### Mandatory

| Brain State | Animation Name | PNG Folder | WebM Path | Playback |
|-------------|---------------|------------|-----------|----------|
| `IDLE` | `idle/stand` | `{skin}_idle_stand/` | `{skin}/idle/stand.webm` | loop |
| `LISTENING` | `idle/still` | `{skin}_idle_still/` | `{skin}/idle/still.webm` | loop |
| `THINKING` | `actions/bubblegum` | `{skin}_action_bubblegum/` | `{skin}/actions/bubblegum.webm` | loop |
| `TALKING` | `actions/breathing` | `{skin}_action_breathing/` | `{skin}/actions/breathing.webm` | loop |
| `PANICKED` | `actions/spinning` | `{skin}_action_spinning/` | `{skin}/actions/spinning.webm` | loop |
| `SLEEPY` | `actions/sleep` | `{skin}_action_sleep/` | `{skin}/actions/sleep.webm` | loop |
| `STUDIOUS` | `actions/screentap` | `{skin}_action_screentap/` | `{skin}/actions/screentap.webm` | loop |
| `TIRED` | `actions/tired` | `{skin}_action_tired/` | `{skin}/actions/tired.webm` | loop |
| `WORKING` | `actions/smartphone` | `{skin}_action_smartphone/` | `{skin}/actions/smartphone.webm` | loop |
| `HAPPY` | `actions/fly` | `{skin}_action_fly/` | `{skin}/actions/fly.webm` | loop |

### Optional (high-value)

| Purpose | PNG Folder | WebM Path | Playback |
|---------|------------|-----------|----------|
| Startup intro | `{skin}_intro_spawn/` | `{skin}/intro/spawn.webm` | one-shot |
| Random idle clips | `{skin}_action_wave/`, `{skin}_action_stretch/`, … | `{skin}/actions/wave.webm` | one-shot |

The brain **auto-discovers** every folder matching `{skin}_action_*` as a random idle action — add as many as you want, they will be picked up automatically on next launch.

---

## Step 3 — Production Workflow

### Option A — Pixel Art (simplest)

```
Aseprite → export PNG sequence → place in folder
```

- Draw each animation state as a separate `.ase` file
- Export via **File → Export Sprite Sheet**: output `frame_0001.png`, `frame_0002.png`, …
- Recommended canvas: **200×200 px** at 2–4× scale, **8–24 frames** per clip

### Option B — Rigged 2D (best quality/effort ratio)

```
Figma / Illustrator → Spine or DragonBones → export PNG sequence or WebM
```

- Design body parts as separate layers
- Rig with bones in Spine/DragonBones
- Animate each state on its own timeline
- Export each state as a PNG sequence or transparent WebM

### Option C — Pre-rendered 3D

```
Blender → render PNG sequences → FFmpeg → WebM
```

- Render against a solid flat background colour (the chroma-key engine reads the top-left pixel as background — see Step 6)
- Convert to WebM after rendering:
  ```bash
  ffmpeg -i rendered_%04d.png -c:v libvpx-vp9 -b:v 0 -crf 33 output.webm
  ```

---

## Step 4 — Folder & File Layout

### PNG layout

```
assets/
└── animations/
    ├── neon_idle_stand/
    │   ├── frame_0001.png
    │   ├── frame_0002.png
    │   └── ...
    ├── neon_idle_still/
    │   └── frame_0001.png      ← single frame is fine for static poses
    ├── neon_action_breathing/
    │   └── ...
    ├── neon_action_spinning/
    │   └── ...
    ├── neon_intro_spawn/       ← optional startup animation
    │   └── ...
    └── neon_action_wave/       ← optional random idle clip
        └── ...
```

### WebM layout (can coexist with PNG)

```
assets/
└── animations/
    └── neon/
        ├── idle/
        │   ├── stand.webm
        │   └── still.webm
        ├── actions/
        │   ├── breathing.webm
        │   ├── spinning.webm
        │   ├── bubblegum.webm
        │   └── wave.webm
        └── intro/
            └── spawn.webm
```

---

## Step 5 — Frame Naming Rules

PNG frames **must** match the glob `frame_*.png` and sort correctly in alphabetical order.

```
frame_0001.png  ✓
frame_0002.png  ✓
frame_01.png    ✗  (breaks sort order once you exceed 9 frames)
```

**Always zero-pad to at least 4 digits.** To batch-rename Blender renders:
```bash
# Rename render_0001.png → frame_0001.png
for f in render_*.png; do mv "$f" "frame_${f#render_}"; done
```

---

## Step 6 — WebM Chroma Key Notes

The engine samples the **top-left pixel (0, 0)** as the background colour and makes all pixels within ±40 per channel transparent.

Rules to follow:
- Use a **solid flat colour** for the background — no gradients, shadows, or anti-aliasing near the top-left corner
- Leave at least **1 px of solid background** at the top-left
- Do not use a background colour that appears on the character itself (e.g. avoid pure green if the character wears green)

Recommended background: `#00FF00` (chroma green) or `#FF00FF` (magenta) — both are easy to avoid in character designs.

---

## Step 7 — Minimum Viable Character (Build Order)

Iterate in this order. Each step gives you a working pet immediately:

1. **`{skin}_idle_stand`** — pet appears on screen and loops
2. **`{skin}_idle_still`** + **`{skin}_action_breathing`** — voice interaction works visually
3. **`{skin}_action_bubblegum`** — thinking state works
4. **Remaining 7 sensor states** — full system reactivity
5. **`{skin}_intro_spawn`** — startup animation plays on launch
6. **Random action clips** — personality and variety during idle

---

## Step 8 — Test Without Restarting

```bash
# Set your skin in config.json
"buddy_skin": "neon"

# Launch in dev mode — brain auto-discovers all neon_* folders on startup
conda run -n kibo python main.py
```

The engine discovers clips at startup, so you only need to restart once per new folder. If a clip is missing, the pet silently stays in `idle/stand` for that state — no crash.

---

## Quick Reference Checklist

```
[ ] Skin name chosen and set in config.json
[ ] neon_idle_stand      — main idle loop
[ ] neon_idle_still      — listening pose
[ ] neon_action_bubblegum — thinking
[ ] neon_action_breathing — talking
[ ] neon_action_spinning  — high CPU / panicked
[ ] neon_action_sleep     — late-night sleepy
[ ] neon_action_screentap — coding / studious
[ ] neon_action_tired     — low battery
[ ] neon_action_smartphone — moderate CPU / working
[ ] neon_action_fly       — happy
[ ] neon_intro_spawn      — (optional) startup animation
[ ] neon_action_*         — (optional) random idle clips
[ ] Frames zero-padded to frame_0001.png
[ ] WebM background is solid flat colour at pixel (0,0)
[ ] conda run -n kibo python main.py — confirmed working
```
