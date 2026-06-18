====================================
  PES6 Settings+   (enhanced settings.exe replacement)
====================================

A drop-in replacement for Pro Evolution Soccer 6's settings.exe. Edits
settings.dat directly: Display, Online, and Device (controller) settings, plus
button mapping, sharable presets, and player-slot assignment.

REQUIREMENT: Python 3.10 or newer (free)
  -> https://www.python.org/downloads/
  -> During install, check "Add Python to PATH"
  (The launcher installs the pygame-ce package automatically if missing; it is
   only needed for the live "press a button to bind" feature.)

HOW TO USE:
  1. Double-click "Launch_PES6_Settings_Plus.bat"
  2. The app auto-loads settings.dat. If yours is elsewhere, click the "..."
     button next to the path to locate it.
  3. Use the Display / Online / Device tabs and click Save/Apply on each.

DEVICE TAB:
  - Lists every controller in settings.dat, named (DualSense, Xbox 360, ...),
    with "- 2" / "- 3" numbering to tell identical pads apart.
  - Assign each controller to a Player slot (1-8) or None (None removes it).
    Picking a slot already in use swaps the two controllers.
  - Edit a controller's button mapping, including live capture (click the pad
    button, then press a control).

PRESETS:
  - Save a controller's mapping to a .pes6preset file (JSON) - safe to share.
  - Apply a preset to any controller, or star one as the default for that
    controller type.
  - Common pads (DualSense, Xbox 360) come with working defaults out of the box
    (created automatically on first run).

BACKUP:
  Before every write the app saves settings.bak next to settings.dat, plus a
  timestamped copy under settings.dat.backups\ (last 20 kept). To restore, copy
  a backup back over settings.dat.

NOTES:
  - settings.dat is always 420 bytes (keyboard + up to 8 controllers).
  - The in-match Local/Visitante assignment is also chosen in-game; this app
    controls which controllers exist as players and their button mappings.

====================================
