# PES6 Settings+

An enhanced, drop-in replacement for **Pro Evolution Soccer 6**'s `settings.exe`.
It edits `settings.dat` directly and does everything the original does — **Display**,
**Online**, and **Device** (controller) settings — plus a lot more: per-controller
button mapping with live capture, a `settings.dat` location picker, sharable
controller presets with per-type defaults, and player-slot assignment. It recomputes
the file checksum so PES 6 accepts the changes without resetting.

![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)

## Download

**[⬇ Download latest release (no Python needed)](https://github.com/Nicorufino/pes6-settings-plus/releases/latest)**

Download `pes6_settings_plus.exe` and run it — no installation required.

---

## Features

### Display
- Screen mode (Window / Full Screen), resolution (from your monitor's modes),
  quality, and brightness.

### Online
- UDP port (with auto-select) and UPnP toggle.

### Device (controllers)
- Detects every controller in `settings.dat` and names it (DualSense, Xbox 360,
  DualShock, …), with `- 2` / `- 3` numbering to tell identical pads apart.
- **Assign each controller to a Player slot** (1–8) or **None**; picking a taken
  slot swaps the two. Setting a controller to **None** removes it.
- **Edit button mappings** per controller, including **live capture** — click the
  🎮 button and press a control to bind it.
- **Presets**: save a controller's mapping to a sharable `.pes6preset` file, apply
  it to any controller, or **⭐ set one as the default for that controller type**.
- **Built-in defaults**: common pads (DualSense, Xbox 360) get working bindings
  out of the box — first run seeds them automatically, no setup needed.

### Safety
- Recomputes the file checksum so PES 6 accepts the file without resetting.
- Writes `settings.bak` plus rolling timestamped backups in `settings.dat.backups\`
  before every change, so your history can't be wiped.

---

## Requirements

- Windows. That's it — download the `.exe` from the
  [releases page](https://github.com/Nicorufino/pes6-settings-plus/releases/latest)
  and run it.
- To run from source: Python 3.10+ and `pygame-ce` (only needed for the live
  button-capture feature): `python -m pip install pygame-ce`.

---

## Usage

1. Launch the app.
2. It auto-loads `settings.dat`. If yours is elsewhere, use the **…** button next
   to the path to locate it.
3. Use the **Display**, **Online**, and **Device** tabs and click the **Save** /
   **Apply** button on each tab.

### Assigning controllers to players
On the **Device** tab, set each controller's dropdown to a Player slot (or None),
then click **Apply assignments**. A newly assigned pad of a known type gets its
default mapping automatically.

> Note: in PES 6, the keyboard is a separate device and the actual in-match
> Local/Visitante assignment is also chosen in-game. The app controls which
> controllers exist as players and their mappings.

---

## File structure

| File | Description |
|---|---|
| `pes6_settings_plus.py` | Main application |
| `*.pes6preset` | Preset files (JSON) — safe to share |
| `settings.bak` / `settings.dat.backups\` | Automatic backups |

---

## How it works

`settings.dat` is a fixed 420-byte binary file:

```
Header(16) + N × [44-byte device block] + filler + upnp(4) + port(4)
```

Each device block is `guid(16) + button mapping(24) + active flag(4)`; the file
holds up to 9 blocks (keyboard + 8 controllers). Display settings live in the
header; the app reads/writes the relevant fields and recalculates the 16-bit
checksum (sum of bytes from offset 4, stored at bytes 2–3) so PES 6 validates the
file.

---

## Backup & recovery

Before every write, the app saves `settings.bak` next to `settings.dat`, plus a
timestamped copy under `settings.dat.backups\` (last 20 kept). To restore, copy a
backup back over `settings.dat`.
