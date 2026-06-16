# PES 6 Controller Preset Manager

A lightweight GUI tool to save, load, and copy controller button mappings in **Pro Evolution Soccer 6** (PC). Useful when playing with multiple controllers of the same type and you want all of them to share the same layout without reconfiguring each one manually inside the game.

![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)

## Download

**[⬇ Download latest release (no Python needed)](https://github.com/Nicorufino/pes6-controller-preset-manager/releases/latest)**

Just download `pes6_preset_manager.exe` and run it — no installation required.

---

## Features

- Detects all controllers registered in `settings.dat` and shows their names (DualSense, Xbox 360, DualShock, etc.)
- Saves a controller's current mapping as a `.pes6preset` file (JSON)
- Applies a saved preset to any controller slot with one click
- Warns you if you try to apply a preset to a controller of a different model
- Automatically updates the file checksum so PES 6 accepts the changes without resetting
- Creates a `settings.bak` backup before every write

---

## Requirements

- Windows

That's it. Download the `.exe` from the [releases page](https://github.com/Nicorufino/pes6-controller-preset-manager/releases/latest) and run it directly.

If you prefer to run from source, you need Python 3.8+ with no additional packages.

---

## Usage

1. Double-click **`Iniciar_PES6_Presets.bat`** to launch the app.
2. The app auto-loads `settings.dat` from:
   `Documents\KONAMI\Pro Evolution Soccer 6\settings.dat`
   If your file is elsewhere, use the **…** button to locate it.
3. Select a controller from the **Detected Controllers** list.
4. **To save a preset:** click *Save preset for selected controller*, give it a name.
5. **To apply a preset** (e.g. copy Player 1's layout to Player 2):
   - Select the **destination** controller in the left panel
   - Select the **preset** in the right panel
   - Click **Apply selected preset to indicated controller**

---

## Important: apply presets to the same controller model

Each controller type (DualSense, Xbox 360, DualShock 4, etc.) uses a different button numbering scheme. **Applying a preset from one model to a different model will cause PES 6 to reset the entire controller configuration** (including resolution and all other slots).

The app detects mismatches and warns you before applying, but the rule of thumb is:

> **DualSense preset → DualSense slot only. Xbox 360 preset → Xbox 360 slot only.**

Presets saved from one physical controller of a given model are fully compatible with any other controller of the same model.

---

## File structure

| File | Description |
|---|---|
| `pes6_preset_manager.py` | Main application |
| `Iniciar_PES6_Presets.bat` | Launcher (double-click to run) |
| `*.pes6preset` | Preset files (JSON) — safe to share |
| `settings.bak` | Auto-backup created before each write |

---

## How it works

`settings.dat` is a 420-byte binary file. Each controller occupies a 44-byte block containing:
- A 16-byte GUID identifying the physical device
- 24 bytes of button/axis mapping

The tool reads and writes only those 24 mapping bytes and recalculates the file's 16-bit checksum (sum of all bytes from offset 4, stored at bytes 2–3) so PES 6 validates the file correctly.

---

## Backup & recovery

Before every write, the app saves a backup to `settings.bak` in the same folder as `settings.dat`. To restore it, simply rename `settings.bak` to `settings.dat`.
