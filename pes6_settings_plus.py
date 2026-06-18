"""
PES6 Settings+

An enhanced, drop-in replacement for Pro Evolution Soccer 6's settings.exe.
Edits settings.dat directly — Display, Online, and Device (controller) settings —
and adds: per-controller button mapping with live capture, a settings.dat location
picker, sharable controller presets with per-type defaults, and player-slot
assignment. Recomputes the file checksum so PES 6 accepts changes without resetting.
"""

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import json, os, shutil, struct
from pathlib import Path
from datetime import datetime

PES_INPUTS = [
    "L2", "L1",
    "D-Pad ←", "D-Pad →",
    "D-Pad ↑", "D-Pad ↓",
    "Axis Y −", "Axis X −", "Axis Y +", "Axis X +",
    "L3", "Button 8",
    "R2", "R1",
    "△", "□", "✕", "○",
    "Rotation Z −", "Axis Z −", "Rotation Z +", "Axis Z +",
    "R3", "Button 9",
]

# Built-in default button mappings per controller type (VID/PID). Applied
# automatically when a controller of that type is newly assigned to a Player
# slot — no manual setup needed. A user-saved starred preset overrides these.
BUILTIN_TYPE_DEFAULTS: dict[str, list[int]] = {
    # Hand-verified in-game mappings (match the shipped presets).
    "VID_054C&PID_0CE6": [20, 22, 23, 21, 8, 9, 10, 11, 18, 19, 16, 17,
                          15, 14, 13, 12, 4, 5, 6, 7, 0, 1, 2, 3],   # DualSense
    "VID_045E&PID_028E": [16, 18, 19, 17, 20, 21, 22, 23, 9, 8, 14, 15,
                          13, 11, 10, 12, 0, 1, 2, 3, 4, 5, 6, 7],   # Xbox 360
}

# Extra built-in presets shipped as OPTIONS (not the auto-applied default).
BUILTIN_EXTRA_PRESETS: list[dict] = [
    {
        "name":    "Dualsense only arrows (for controllers with left stick drift)",
        "vid_pid": "VID_054C&PID_0CE6",
        "hint":    "DualSense Wireless Controller",
        "mapping": [20, 22, 23, 21, 255, 255, 255, 255, 18, 19, 16, 17,
                    15, 14, 13, 12, 8, 10, 11, 9, 0, 1, 2, 3],
    },
]

# ── File layout (FIXED 420 bytes) ─────────────────────────────────────────────
# settings.dat =
#   Header(16)                              @ 0x00
#   N × [44-byte device block]              @ 0x10   (keyboard first; N up to 9)
#   filler (calibration scratch, ignored)  fills the gap
#   upnp(4) + port(4)                       @ 0x19C  (always the LAST 8 bytes)
# Total is always 420. A device block = guid(16) + mapping(24) + active(4).
# Each block's `active` flag (offset 40, uint32) = 1 player / 0 idle.
# With the max 9 blocks (keyboard + 8 controllers) the blocks reach 0x19C, so the
# last block's active flag lands on 0x198 — the same spot as `udp_auto`; PES packs
# them. `udp_auto` is therefore only independent when there are ≤ 8 blocks.
FILE_SIZE       = 420
HEADER_SIZE     = 16
BLOCK_SIZE      = 44
MAPPING_OFF     = 0x10
MAPPING_SIZE    = 24
ACTIVE_OFF      = 40    # uint32 in each block: 1 = active player, 0 = registered/idle
ONLINE_TAIL     = 8     # upnp(4) + port(4) — always the last 8 bytes
DEVICE_END      = FILE_SIZE - ONLINE_TAIL          # 412 / 0x19C
MAX_BLOCKS      = (DEVICE_END - HEADER_SIZE) // BLOCK_SIZE   # 9 = keyboard + 8
MAX_PLAYERS     = 8     # keyboard is separate; controllers are Player 1..8
UNASSIGNED      = 0xFF
PRESET_EXT      = ".pes6preset"
BACKUP_NAME     = "settings.bak"
KEYBOARD_GUID   = "612b1d6fa0d5cf11bfc7444553540000"
MODEL_FAMILY_OFF = 6
MODEL_FAMILY_LEN = 2
FILLER_BYTE     = 0xFF  # used to pad filler when block count shrinks

# ── Header settings offsets (fixed, confirmed by diffing settings.exe) ─────────
# 0x02-03 is a checksum = sum(data[4:]) & 0xFFFF, recomputed on every write.
OFF_VERSION    = 0x00
OFF_WIDTH      = 0x04   # uint16
OFF_HEIGHT     = 0x06   # uint16
OFF_SCREENMODE = 0x08   # 1 byte — 0=Window, 1=Full Screen
OFF_BRIGHTNESS = 0x09   # 1 byte — 0=Dark … 10=default … 20=Bright
OFF_QUALITY    = 0x0A   # 1 byte — 0=Low, 1=Medium, 2=High
OFF_UDP_AUTO   = 0x198  # uint32 (overlaps block 8's active flag when 8 controllers)
OFF_UPNP       = 0x19C  # uint32 — 0=off, 1=on
OFF_UDP_PORT   = 0x1A0  # uint32 — default 5739

SCREEN_MODES = ["Window", "Full Screen"]
QUALITY_LEVELS = ["Low", "Medium", "High"]
BRIGHTNESS_MIN, BRIGHTNESS_MAX, BRIGHTNESS_DEFAULT = 0, 20, 10
DEFAULT_UDP_PORT = 5739
SCREENMODE_VERIFIED = True    # confirmed via diff: 0x08 = 0 Window / 1 Full Screen

DEFAULT_DAT = (Path.home() / "Documents" / "KONAMI"
               / "Pro Evolution Soccer 6" / "settings.dat")

DEFAULT_PRESETS_DIR = Path.home() / "Documents" / "PES 6 Controller Presets"

BG, BG2, BG3 = "#1e1e2e", "#313244", "#45475a"
FG, FG2, ACC, GRN, YEL, RED = "#cdd6f4", "#a6adc8", "#89b4fa", "#a6e3a1", "#f9e2af", "#f38ba8"

# ── Known device names by VID&PID ─────────────────────────────────────────────
# Source: USB HID device list + community knowledge
KNOWN_DEVICES: dict[str, str] = {
    "VID_054C&PID_0CE6": "DualSense Wireless Controller",
    "VID_054C&PID_09CC": "DualShock 4 (CUH-ZCT2)",
    "VID_054C&PID_05C4": "DualShock 4 (CUH-ZCT1)",
    "VID_054C&PID_0268": "DualShock 3",
    "VID_054C&PID_0DF2": "DualSense Edge",
    "VID_045E&PID_028E": "Xbox 360 Controller",
    "VID_045E&PID_02FF": "Xbox 360 Controller",
    "VID_045E&PID_0B12": "Xbox Series X|S Controller",
    "VID_045E&PID_02EA": "Xbox One Controller",
    "VID_045E&PID_02FD": "Xbox One Controller (BT)",
    "VID_045E&PID_0719": "Xbox 360 Wireless Receiver",
    "VID_046D&PID_C216": "Logitech F310",
    "VID_046D&PID_C218": "Logitech F510",
    "VID_046D&PID_C219": "Logitech F710",
    "VID_046D&PID_C21D": "Logitech F310",
    "VID_046D&PID_C21E": "Logitech F510",
    "VID_046D&PID_C21F": "Logitech F710",
    "VID_046D&PID_C2AB": "Logitech G HUB G13",
    "VID_2DC8&PID_301B": "8BitDo Ultimate 2C Wireless Controller",
    "VID_2DC8&PID_3106": "8BitDo Pro 2",
    "VID_2DC8&PID_3107": "8BitDo Ultimate",
    "VID_2DC8&PID_6012": "8BitDo Ultimate 2 Wireless Controller",
    "VID_2DC8&PID_6001": "8BitDo SN30 Pro",
    "VID_0F0D&PID_00C1": "HORI Pad",
    "VID_0F0D&PID_0092": "HORI Fighting Commander",
    "VID_0738&PID_4726": "Mad Catz Xbox 360 Controller",
    "VID_1532&PID_0900": "Razer Onza",
    "VID_1532&PID_0A00": "Razer Sabertooth",
}

# ── Lookup guid → name and VID/PID via the Windows registry ──────────────────

_device_names:   dict[str, str] | None = None   # guid_hex → friendly name
_guid_vid_pid:   dict[str, str] | None = None   # guid_hex → "VID_XXXX&PID_XXXX"
_vid_pid_guids:  dict[str, list[str]] | None = None  # "VID_XXXX&PID_XXXX" → ordered guid list


def _normalize_vid_pid(raw: str) -> str:
    import re
    upper = raw.upper()
    m = re.search(r'VID_([0-9A-F]{4}).*?PID_([0-9A-F]{4})', upper)
    if m:
        return f"VID_{m.group(1)}&PID_{m.group(2)}"
    m = re.search(r'VID&[0-9A-F]*?([0-9A-F]{4})_PID(?:&[0-9A-F]*?([0-9A-F]{4}))?', upper)
    if m:
        return f"VID_{m.group(1)}&PID_{m.group(2) or '0000'}"
    return ""


def _build_name_cache() -> tuple[dict[str, str], dict[str, str], dict[str, list[str]]]:
    names:    dict[str, str] = {}
    vid_pids: dict[str, str] = {}
    vp_guids: dict[str, list[str]] = {}
    try:
        import winreg
        BASE = (r"SYSTEM\CurrentControlSet\Control\MediaProperties"
                r"\PrivateProperties\DirectInput")
        root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, BASE)

        i = 0
        while True:
            try:
                vid_pid = winreg.EnumKey(root, i); i += 1
            except OSError:
                break

            vid_pid_clean = _normalize_vid_pid(vid_pid) or vid_pid.upper()
            friendly = KNOWN_DEVICES.get(vid_pid_clean, vid_pid_clean)

            try:
                cal_key = winreg.OpenKey(root, vid_pid + r"\Calibration")
                j = 0
                while True:
                    try:
                        idx = winreg.EnumKey(cal_key, j); j += 1
                    except OSError:
                        break
                    try:
                        idx_key = winreg.OpenKey(cal_key, idx)
                        guid_bytes, _ = winreg.QueryValueEx(idx_key, "GUID")
                        if isinstance(guid_bytes, bytes) and len(guid_bytes) == 16:
                            ghex = guid_bytes.hex()
                            names[ghex]    = friendly
                            vid_pids[ghex] = vid_pid_clean
                            vp_guids.setdefault(vid_pid_clean, []).append(ghex)
                        winreg.CloseKey(idx_key)
                    except OSError:
                        pass
                winreg.CloseKey(cal_key)
            except OSError:
                pass

        winreg.CloseKey(root)
    except Exception:
        pass
    return names, vid_pids, vp_guids


def _ensure_cache() -> None:
    global _device_names, _guid_vid_pid, _vid_pid_guids
    if _device_names is None:
        _device_names, _guid_vid_pid, _vid_pid_guids = _build_name_cache()


def lookup_device_name(guid_hex: str) -> str:
    _ensure_cache()
    return (_device_names or {}).get(guid_hex, "")


def lookup_vid_pid(guid_hex: str) -> str:
    _ensure_cache()
    return (_guid_vid_pid or {}).get(guid_hex, "")


def _get_connected_counts() -> dict[str, int]:
    """Count started HID device instances per VID/PID.
    Uses HID bus only — accurately reflects per-instance connection state
    for both USB and Bluetooth controllers."""
    import ctypes, winreg
    counts: dict[str, int] = {}
    try:
        cfgmgr = ctypes.WinDLL("cfgmgr32")
        DN_STARTED = 0x00000008

        def _is_started(instance_id: str) -> bool:
            dev = ctypes.c_ulong()
            if cfgmgr.CM_Locate_DevNodeW(ctypes.byref(dev),
                                          ctypes.create_unicode_buffer(instance_id), 0) != 0:
                return False
            status = ctypes.c_ulong()
            problem = ctypes.c_ulong()
            if cfgmgr.CM_Get_DevNode_Status(ctypes.byref(status),
                                             ctypes.byref(problem), dev, 0) != 0:
                return False
            return bool(status.value & DN_STARTED)

        hid_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                  r"SYSTEM\CurrentControlSet\Enum\HID")
        i = 0
        while True:
            try:
                dev_name = winreg.EnumKey(hid_key, i); i += 1
            except OSError:
                break
            vp = _normalize_vid_pid(dev_name)
            if not vp:
                continue
            try:
                inst_key = winreg.OpenKey(hid_key, dev_name)
                j = 0
                while True:
                    try:
                        instance = winreg.EnumKey(inst_key, j); j += 1
                    except OSError:
                        break
                    if _is_started(f"HID\\{dev_name}\\{instance}"):
                        counts[vp] = counts.get(vp, 0) + 1
                winreg.CloseKey(inst_key)
            except OSError:
                pass
        winreg.CloseKey(hid_key)
    except Exception:
        pass
    return counts


def is_guid_connected(guid_hex: str) -> bool:
    """True if this specific controller instance is currently connected.
    Uses position within its VID/PID group vs. the count of connected instances."""
    _ensure_cache()
    vp = (_guid_vid_pid or {}).get(guid_hex)
    if not vp:
        return False
    counts = _get_connected_counts()
    n = counts.get(vp, 0)
    guids = (_vid_pid_guids or {}).get(vp, [])
    try:
        return guids.index(guid_hex) < n
    except ValueError:
        return False


# ── file I/O ──────────────────────────────────────────────────────────────────

def _guid_str(b: bytes) -> str:
    d1 = struct.unpack_from('<I', b, 0)[0]
    d2 = struct.unpack_from('<H', b, 4)[0]
    d3 = struct.unpack_from('<H', b, 6)[0]
    d4 = b[8:16].hex().upper()
    return f"{{{d1:08X}-{d2:04X}-{d3:04X}-{d4[:4]}-{d4[4:]}}}"


def _model_family(guid_hex: str) -> str:
    b = bytes.fromhex(guid_hex)
    return b[MODEL_FAMILY_OFF : MODEL_FAMILY_OFF + MODEL_FAMILY_LEN].hex()


def _count_blocks(data: bytes) -> int:
    """Number of device blocks, detected by the DEST signature at block+0x0A.
    Blocks may run right up to the upnp/port tail (DEVICE_END = 0x19C)."""
    n = 0
    while True:
        bs = HEADER_SIZE + n * BLOCK_SIZE
        if bs + BLOCK_SIZE > DEVICE_END:
            break
        if data[bs + 0x0A : bs + 0x0E] != b'DEST':
            break
        n += 1
    return n


def _validate(data: bytes, path: Path) -> None:
    if len(data) != FILE_SIZE:
        raise ValueError(
            f"Wrong size ({len(data)} bytes, expected {FILE_SIZE}).\n"
            f"This does not appear to be a controller settings.dat.\nFile: {path}")
    if data[HEADER_SIZE + 0x0A : HEADER_SIZE + 0x0E] != b'DEST':
        raise ValueError(
            f"Controller signature not found.\n"
            f"Are you pointing to the correct settings.dat?\nFile: {path}")


def parse_dat(path: Path) -> list[dict]:
    data = path.read_bytes()
    _validate(data, path)
    result = []
    n_total = _count_blocks(data)
    for n in range(n_total):
        bs = HEADER_SIZE + n * BLOCK_SIZE
        guid    = data[bs : bs + 16]
        ghex    = guid.hex()
        mapping = list(data[bs + MAPPING_OFF : bs + MAPPING_OFF + MAPPING_SIZE])
        is_kb   = ghex == KEYBOARD_GUID
        active  = struct.unpack_from('<I', data, bs + ACTIVE_OFF)[0] != 0
        result.append({
            "index":        n,
            "block_start":  bs,
            "guid_hex":     ghex,
            "guid_str":     _guid_str(guid),
            "model_family": _model_family(ghex),
            "device_name":  lookup_device_name(ghex),
            "mapping":      mapping,
            "is_keyboard":  is_kb,
            "active":       active,
            "connected":    is_kb or is_guid_connected(ghex),
        })
    return result


def _update_checksum(data: bytearray) -> None:
    csum = sum(data[4:]) & 0xFFFF
    data[2] = csum & 0xFF
    data[3] = (csum >> 8) & 0xFF


def _assert_sane(data: bytes, path: Path) -> None:
    """Safety net before any write: correct size, valid first-block signature, and
    not the corruption pattern (every controller collapsed to one identical GUID).
    NOTE: intentional duplicates are allowed — settings.exe reuses a physical pad
    across several player slots when there are fewer pads than players."""
    _validate(data, path)
    n = _count_blocks(data)
    ctrl_guids = [data[HEADER_SIZE + i*BLOCK_SIZE: HEADER_SIZE + i*BLOCK_SIZE + 16].hex()
                  for i in range(n)
                  if data[HEADER_SIZE + i*BLOCK_SIZE: HEADER_SIZE + i*BLOCK_SIZE + 16].hex()
                  != KEYBOARD_GUID]
    if len(ctrl_guids) >= 3 and len(set(ctrl_guids)) == 1:
        raise ValueError(
            "Refusing to write: all controllers collapsed to one GUID "
            "(corruption). Operation aborted; your file is unchanged.")


def write_mapping(path: Path, slot: int, mapping: list[int]) -> None:
    data = bytearray(path.read_bytes())
    _validate(bytes(data), path)
    ctrls = parse_dat(path)
    if slot >= len(ctrls):
        raise ValueError(f"Slot {slot} does not exist ({len(ctrls)} entries).")
    if ctrls[slot]["is_keyboard"]:
        raise ValueError("Cannot modify the system keyboard.")
    bs = ctrls[slot]["block_start"]
    for i, b in enumerate(mapping):
        data[bs + MAPPING_OFF + i] = b & 0xFF
    _update_checksum(data)
    _assert_sane(bytes(data), path)
    path.write_bytes(bytes(data))


def _decompose(data: bytes) -> tuple[bytes, list[dict], bytes, bytes]:
    """Split into (header, [{guid_hex, block}], filler, online_tail).
    Layout: header(16) + N blocks(44) + filler + upnp/port(8). The filler is the
    calibration scratch between the blocks and the fixed last-8-byte online tail.
    Reassemble with _compose()."""
    n = _count_blocks(data)
    blocks_end = HEADER_SIZE + n * BLOCK_SIZE
    header = data[:HEADER_SIZE]
    filler = bytes(data[blocks_end:DEVICE_END])
    online_tail = bytes(data[DEVICE_END:FILE_SIZE])   # upnp(4) + port(4)
    devices = [{"guid_hex": data[HEADER_SIZE + i*BLOCK_SIZE: HEADER_SIZE + i*BLOCK_SIZE + 16].hex(),
                "block":    bytes(data[HEADER_SIZE + i*BLOCK_SIZE: HEADER_SIZE + (i+1)*BLOCK_SIZE])}
               for i in range(n)]
    return header, devices, filler, online_tail


def _compose(header: bytes, devices: list[dict], filler: bytes, online_tail: bytes) -> bytes:
    """Rebuild a fixed 420-byte settings.dat from parts. Filler is padded/trimmed
    at its FRONT (preserving its tail, where udp_auto lives) so the blocks and the
    last-8-byte online tail stay correctly placed. Checksum recomputed."""
    n = len(devices)
    if n > MAX_BLOCKS:
        raise ValueError(f"Too many devices ({n}); the file holds at most "
                         f"{MAX_BLOCKS} (keyboard + {MAX_PLAYERS} controllers).")
    out = bytearray(header)
    out += b"".join(d["block"] for d in devices)
    need = DEVICE_END - len(out)          # filler bytes required before the tail
    if need < 0:
        raise ValueError("Device blocks overflow the online tail.")
    if len(filler) >= need:
        f = filler[len(filler) - need:]                       # keep filler's tail
    else:
        f = bytes([FILLER_BYTE]) * (need - len(filler)) + filler
    out += f
    out += online_tail
    if len(out) != FILE_SIZE:
        raise ValueError(f"Internal error: composed {len(out)} bytes, expected {FILE_SIZE}.")
    _update_checksum(out)
    return bytes(out)


def _write_safely(data: bytes, path: Path) -> None:
    _assert_sane(data, path)
    path.write_bytes(data)


def add_controller(path: Path, guid_hex: str, mapping: list[int] | None = None) -> None:
    """Add a new device (block + axis entry) for `guid_hex` (32-char DInput GUID).
    The block is cloned from an existing same-model block so PES accepts it; the
    axis entry is cloned from that model too (else left uncalibrated)."""
    data = path.read_bytes()
    _validate(data, path)
    header, devices, filler, online = _decompose(data)
    if any(d["guid_hex"] == guid_hex for d in devices):
        raise ValueError("That controller is already in this settings.dat.")
    n_players = sum(1 for d in devices if d["guid_hex"] != KEYBOARD_GUID)
    if n_players >= MAX_PLAYERS:
        raise ValueError(f"PES supports at most {MAX_PLAYERS} controllers "
                         f"(Player 1–{MAX_PLAYERS}). Remove one first.")
    devices.append(_make_device(guid_hex, devices, mapping))
    _write_safely(_compose(header, devices, filler, online), path)


def _make_device(guid_hex: str, devices: list[dict],
                 mapping: list[int] | None = None) -> dict:
    """Build a new device dict (block), cloning layout from a same-model block so
    PES accepts it. `mapping` overrides the cloned button mapping."""
    guid = bytes.fromhex(guid_hex)
    if len(guid) != 16 or guid[0x0A:0x0E] != b"DEST":
        raise ValueError("Not a valid DirectInput controller GUID.")
    fam = guid_hex[MODEL_FAMILY_OFF*2:(MODEL_FAMILY_OFF+MODEL_FAMILY_LEN)*2]
    ref = next((d for d in devices if d["guid_hex"] != KEYBOARD_GUID
                and _model_family(d["guid_hex"]) == fam), None) \
        or next((d for d in devices if d["guid_hex"] != KEYBOARD_GUID), None) \
        or (devices[0] if devices else None)
    if ref is None:
        raise ValueError("Need at least one existing block to clone the layout from.")
    block = bytearray(ref["block"])
    block[0:16] = guid
    if mapping is not None:
        for i, b in enumerate(mapping[:MAPPING_SIZE]):
            block[MAPPING_OFF + i] = b & 0xFF
    return {"guid_hex": guid_hex, "block": bytes(block)}


def _with_active(dev: dict, active: bool) -> dict:
    """Return a copy of `dev` with its block's active flag set."""
    block = bytearray(dev["block"])
    struct.pack_into('<I', block, ACTIVE_OFF, 1 if active else 0)
    return {**dev, "block": bytes(block)}


def _with_mapping(dev: dict, mapping: list[int]) -> dict:
    """Return a copy of `dev` with its button mapping replaced."""
    block = bytearray(dev["block"])
    for i, b in enumerate(mapping[:MAPPING_SIZE]):
        block[MAPPING_OFF + i] = b & 0xFF
    return {**dev, "block": bytes(block)}


def remove_controller(path: Path, guid_hex: str) -> None:
    """Remove a device (block + axis); filler grows so the file stays 420 bytes."""
    data = path.read_bytes()
    _validate(data, path)
    header, devices, filler, online = _decompose(data)
    if guid_hex == KEYBOARD_GUID:
        raise ValueError("Cannot remove the system keyboard.")
    if not any(d["guid_hex"] == guid_hex for d in devices):
        raise ValueError("That controller is not in this settings.dat.")
    devices = [d for d in devices if d["guid_hex"] != guid_hex]
    _write_safely(_compose(header, devices, filler, online), path)


def reorder_controllers(path: Path, guid_order: list[str]) -> None:
    """Reorder devices so player slots follow `guid_order` (non-keyboard guids,
    Player 1 first). Each device's block AND axis entry move together; the
    keyboard keeps its position."""
    data = path.read_bytes()
    _validate(data, path)
    header, devices, filler, online = _decompose(data)
    by_guid = {d["guid_hex"]: d for d in devices}
    ctrl_guids = [d["guid_hex"] for d in devices if d["guid_hex"] != KEYBOARD_GUID]
    if sorted(guid_order) != sorted(ctrl_guids):
        raise ValueError("guid_order must contain exactly the controllers in the file.")

    new_iter = iter(guid_order)
    ordered = [by_guid[d["guid_hex"]] if d["guid_hex"] == KEYBOARD_GUID
               else by_guid[next(new_iter)] for d in devices]
    _write_safely(_compose(header, ordered, filler, online), path)


def set_player_assignments(path: Path, assignments: list[tuple[str, int]],
                           presets: dict[str, list[int]] | None = None) -> None:
    """Set Player-slot assignments the way settings.exe does: keep EVERY
    registered device block, and toggle each block's active flag (offset 40).

    `assignments` = list of (guid_hex, slot), slot 1..MAX_PLAYERS.
      • Assigned controllers  → active=1, ordered by slot (block order = player #).
      • All other controllers → kept in the file with active=0 (unassigned).
      • The keyboard is always kept and forced active.
      • A controller not yet in the file is added (if there is room) — this is the
        only case that changes block count.
    `presets[guid_hex]` overrides a controller's button mapping (used for newly
    assigned pads)."""
    data = path.read_bytes()
    _validate(data, path)
    header, devices, filler, online = _decompose(data)
    presets = presets or {}

    # One pad per player: collapse to DISTINCT controllers (first block per GUID).
    # This also cleans up any duplicate blocks settings.exe leaves from pad-reuse.
    distinct: list[dict] = []
    seen: set[str] = set()
    for d in devices:
        if d["guid_hex"] == KEYBOARD_GUID or d["guid_hex"] in seen:
            continue
        seen.add(d["guid_hex"]); distinct.append(d)
    by_guid = {d["guid_hex"]: d for d in distinct}

    chosen = [(g, s) for g, s in assignments if g != KEYBOARD_GUID and s]
    slots = [s for _, s in chosen]
    if len(slots) != len(set(slots)):
        raise ValueError("Two controllers are assigned to the same player slot.")
    if len(chosen) > MAX_PLAYERS:
        raise ValueError(f"At most {MAX_PLAYERS} controllers can be assigned.")
    assigned_guids = {g for g, _ in chosen}

    # Keyboard: keep one copy, always active.
    kb_devs = [_with_active(d, True) for d in devices
               if d["guid_hex"] == KEYBOARD_GUID][:1]

    # Active controllers, ordered by player slot.
    active_devs = []
    for guid_hex, _slot in sorted(chosen, key=lambda x: x[1]):
        d = by_guid.get(guid_hex) or _make_device(guid_hex, distinct or devices)
        if guid_hex in presets:
            d = _with_mapping(d, presets[guid_hex])
        active_devs.append(_with_active(d, True))

    # Controllers set to None are DELETED entirely (their block is dropped, not
    # just marked inactive) — a connected pad with an inactive block still gets
    # re-shown by the game, so removing the block is the only way to unassign it.
    new_devices = kb_devs + active_devs
    if len(new_devices) > MAX_BLOCKS:
        raise ValueError(
            f"No room for a new controller — the file already holds {MAX_BLOCKS} "
            f"devices. Unassign one you don't use.")
    _write_safely(_compose(header, new_devices, filler, online), path)


# ── global settings I/O (Display + Online) ────────────────────────────────────

def parse_settings(path: Path) -> dict:
    """Read the Display + Online settings from settings.dat."""
    data = path.read_bytes()
    _validate(data, path)
    return {
        "width":      struct.unpack_from('<H', data, OFF_WIDTH)[0],
        "height":     struct.unpack_from('<H', data, OFF_HEIGHT)[0],
        "screenmode": data[OFF_SCREENMODE],
        "brightness": data[OFF_BRIGHTNESS],
        "quality":    data[OFF_QUALITY],
        "udp_auto":   struct.unpack_from('<I', data, OFF_UDP_AUTO)[0],
        "upnp":       struct.unpack_from('<I', data, OFF_UPNP)[0],
        "udp_port":   struct.unpack_from('<I', data, OFF_UDP_PORT)[0],
    }


def write_settings(path: Path, **fields) -> None:
    """Write any subset of Display/Online fields, then recompute the checksum.
    Accepts: width, height, screenmode, brightness, quality,
             udp_auto, upnp, udp_port."""
    data = bytearray(path.read_bytes())
    _validate(bytes(data), path)
    if "width" in fields:
        struct.pack_into('<H', data, OFF_WIDTH, int(fields["width"]) & 0xFFFF)
    if "height" in fields:
        struct.pack_into('<H', data, OFF_HEIGHT, int(fields["height"]) & 0xFFFF)
    if "screenmode" in fields:
        data[OFF_SCREENMODE] = int(fields["screenmode"]) & 0xFF
    if "brightness" in fields:
        data[OFF_BRIGHTNESS] = max(BRIGHTNESS_MIN,
                                   min(BRIGHTNESS_MAX, int(fields["brightness"]))) & 0xFF
    if "quality" in fields:
        data[OFF_QUALITY] = int(fields["quality"]) & 0xFF
    if "udp_auto" in fields:
        struct.pack_into('<I', data, OFF_UDP_AUTO, int(fields["udp_auto"]) & 0xFFFFFFFF)
    if "upnp" in fields:
        struct.pack_into('<I', data, OFF_UPNP, int(fields["upnp"]) & 0xFFFFFFFF)
    if "udp_port" in fields:
        struct.pack_into('<I', data, OFF_UDP_PORT, int(fields["udp_port"]) & 0xFFFFFFFF)
    _update_checksum(data)
    _assert_sane(bytes(data), path)
    path.write_bytes(bytes(data))


def list_display_modes() -> list[tuple[int, int]]:
    """Enumerate the monitor's supported resolutions via the Windows API —
    the same approach the original settings.exe uses (EnumDisplaySettingsW).
    Returns a sorted, de-duplicated list of (width, height)."""
    import ctypes

    class DEVMODE(ctypes.Structure):
        _fields_ = [
            ("dmDeviceName",       ctypes.c_wchar * 32),
            ("dmSpecVersion",      ctypes.c_ushort),
            ("dmDriverVersion",    ctypes.c_ushort),
            ("dmSize",             ctypes.c_ushort),
            ("dmDriverExtra",      ctypes.c_ushort),
            ("dmFields",           ctypes.c_ulong),
            ("dmOrientation",      ctypes.c_short),
            ("dmPaperSize",        ctypes.c_short),
            ("dmPaperLength",      ctypes.c_short),
            ("dmPaperWidth",       ctypes.c_short),
            ("dmScale",            ctypes.c_short),
            ("dmCopies",           ctypes.c_short),
            ("dmDefaultSource",    ctypes.c_short),
            ("dmPrintQuality",     ctypes.c_short),
            ("dmColor",            ctypes.c_short),
            ("dmDuplex",           ctypes.c_short),
            ("dmYResolution",      ctypes.c_short),
            ("dmTTOption",         ctypes.c_short),
            ("dmCollate",          ctypes.c_short),
            ("dmFormName",         ctypes.c_wchar * 32),
            ("dmLogPixels",        ctypes.c_ushort),
            ("dmBitsPerPel",       ctypes.c_ulong),
            ("dmPelsWidth",        ctypes.c_ulong),
            ("dmPelsHeight",       ctypes.c_ulong),
            ("dmDisplayFlags",     ctypes.c_ulong),
            ("dmDisplayFrequency", ctypes.c_ulong),
            ("dmICMMethod",        ctypes.c_ulong),
            ("dmICMIntent",        ctypes.c_ulong),
            ("dmMediaType",        ctypes.c_ulong),
            ("dmDitherType",       ctypes.c_ulong),
            ("dmReserved1",        ctypes.c_ulong),
            ("dmReserved2",        ctypes.c_ulong),
            ("dmPanningWidth",     ctypes.c_ulong),
            ("dmPanningHeight",    ctypes.c_ulong),
        ]

    modes: set[tuple[int, int]] = set()
    try:
        user32 = ctypes.windll.user32
        dm = DEVMODE()
        dm.dmSize = ctypes.sizeof(DEVMODE)
        i = 0
        while user32.EnumDisplaySettingsW(None, i, ctypes.byref(dm)):
            if dm.dmBitsPerPel >= 16:
                modes.add((int(dm.dmPelsWidth), int(dm.dmPelsHeight)))
            i += 1
    except Exception:
        pass
    if not modes:
        modes = {(640, 480), (800, 600), (1024, 768), (1280, 720),
                 (1280, 1024), (1366, 768), (1600, 900), (1920, 1080)}
    return sorted(modes)


# ── preset I/O ───────────────────────────────────────────────────────────────

def save_preset(path: Path, name: str, mapping: list,
                hint: str = "", model_family: str = "",
                vid_pid: str = "", default_for_type: bool = False) -> None:
    path.write_text(json.dumps({
        "name":             name,
        "controller_hint":  hint,
        "model_family":     model_family,
        "vid_pid":          vid_pid,
        "default_for_type": default_for_type,
        "created":          datetime.now().isoformat(timespec="seconds"),
        "mapping":          mapping,
        "labels":           PES_INPUTS,
    }, indent=2, ensure_ascii=False), encoding="utf-8")


def load_preset(path: Path) -> dict:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if "mapping" not in obj or len(obj["mapping"]) != MAPPING_SIZE:
        raise ValueError("Invalid preset or unsupported version.")
    obj.setdefault("vid_pid", "")
    obj.setdefault("default_for_type", False)
    return obj


def default_preset_for_vidpid(presets_dir: Path, vid_pid: str) -> list[int] | None:
    """Return the mapping of the preset starred as default for `vid_pid`, or None."""
    if not vid_pid or not presets_dir.exists():
        return None
    for f in sorted(presets_dir.glob(f"*{PRESET_EXT}")):
        try:
            obj = load_preset(f)
        except Exception:
            continue
        if obj.get("default_for_type") and obj.get("vid_pid") == vid_pid:
            return obj["mapping"]
    return None


def type_default_mapping(presets_dir: Path, vid_pid: str) -> list[int] | None:
    """Default mapping for a controller type: a user's starred preset takes
    priority, otherwise the app's built-in default for that VID/PID."""
    return (default_preset_for_vidpid(presets_dir, vid_pid)
            or BUILTIN_TYPE_DEFAULTS.get(vid_pid))


def seed_builtin_presets(presets_dir: Path) -> int:
    """Create starred default presets for the built-in controller types, so users
    of common pads (DualSense, Xbox 360, …) get working bindings out of the box —
    no need to make their own. Only creates a preset for a type that doesn't
    already have a default; never overwrites the user's presets. Returns how many
    were created."""
    try:
        presets_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return 0
    have_default = set()
    for f in presets_dir.glob(f"*{PRESET_EXT}"):
        try:
            o = load_preset(f)
        except Exception:
            continue
        if o.get("default_for_type") and o.get("vid_pid"):
            have_default.add(o["vid_pid"])
    existing_names = set()
    for f in presets_dir.glob(f"*{PRESET_EXT}"):
        try:
            existing_names.add(load_preset(f).get("name", ""))
        except Exception:
            pass

    def _safe(s: str) -> str:
        return "".join(c if c.isalnum() or c in " _-" else "_" for c in s)

    created = 0
    # Default presets (one per controller type), starred.
    for vid_pid, mapping in BUILTIN_TYPE_DEFAULTS.items():
        if vid_pid in have_default:
            continue
        name = KNOWN_DEVICES.get(vid_pid, vid_pid)
        dest = presets_dir / f"{_safe(name)} (default){PRESET_EXT}"
        if dest.exists():
            continue
        try:
            save_preset(dest, name, list(mapping), hint=name,
                        vid_pid=vid_pid, default_for_type=True)
            created += 1
        except Exception:
            pass
    # Extra preset OPTIONS (not defaults), seeded once by name.
    for p in BUILTIN_EXTRA_PRESETS:
        if p["name"] in existing_names:
            continue
        dest = presets_dir / f"{_safe(p['name'])}{PRESET_EXT}"
        if dest.exists():
            continue
        try:
            save_preset(dest, p["name"], list(p["mapping"]),
                        hint=p.get("hint", ""), vid_pid=p.get("vid_pid", ""),
                        default_for_type=False)
            created += 1
        except Exception:
            pass
    return created


# ── live controller input (pygame-ce) ─────────────────────────────────────────

_pygame = None
_pygame_ready = False


def _ensure_pygame():
    """Import and init pygame-ce once. Returns the module or None."""
    global _pygame, _pygame_ready
    if _pygame_ready:
        return _pygame
    _pygame_ready = True
    try:
        import os
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        pygame.init()
        pygame.joystick.init()
        _pygame = pygame
    except Exception:
        _pygame = None
    return _pygame


def sdl_guid_vidpid(sdl_guid: str) -> str:
    """Extract 'VID_xxxx&PID_xxxx' from an SDL/pygame joystick GUID."""
    try:
        b = bytes.fromhex(sdl_guid)
        vid = int.from_bytes(b[4:6], "little")
        pid = int.from_bytes(b[8:10], "little")
        if vid:
            return f"VID_{vid:04X}&PID_{pid:04X}"
    except Exception:
        pass
    return ""


_joysticks: dict[int, object] = {}


def open_joysticks() -> list:
    """Return the currently connected pygame joystick objects (or []).
    Joystick handles are cached and reused — re-initialising the subsystem on
    every call drops devices until SDL re-pumps hotplug events."""
    pg = _ensure_pygame()
    if not pg:
        return []
    if not pg.joystick.get_init():
        pg.joystick.init()
    pg.event.pump()   # refresh device list / hotplug state
    js = []
    for i in range(pg.joystick.get_count()):
        j = _joysticks.get(i)
        if j is None:
            try:
                j = pg.joystick.Joystick(i)
            except Exception:
                continue
            _joysticks[i] = j
        js.append(j)
    # drop stale cached handles for unplugged devices
    for i in list(_joysticks):
        if i >= pg.joystick.get_count():
            _joysticks.pop(i, None)
    return js


def poll_input_event(joysticks, axis_threshold: float = 0.6):
    """Pump pygame events and return the first activation from any joystick in
    `joysticks` (a single joystick or a list) as a tuple, or None.
      ('button', idx) | ('axis', idx, +1/-1) | ('hat', idx, (x, y))
    Listening to every matching device means identical controllers can't be
    'picked wrong' — whichever one the user presses is captured."""
    pg = _ensure_pygame()
    if not pg:
        return None
    if not isinstance(joysticks, (list, tuple)):
        joysticks = [joysticks]
    jids = {j.get_instance_id() for j in joysticks}
    for ev in pg.event.get():
        if jids and getattr(ev, "instance_id", None) not in jids:
            continue
        if ev.type == pg.JOYBUTTONDOWN:
            return ("button", ev.button)
        if ev.type == pg.JOYHATMOTION and ev.value != (0, 0):
            return ("hat", ev.hat, ev.value)
        if ev.type == pg.JOYAXISMOTION and abs(ev.value) >= axis_threshold:
            return ("axis", ev.axis, 1 if ev.value > 0 else -1)
    return None


def describe_input(inp) -> str:
    if not inp:
        return "—"
    if inp[0] == "button":
        return f"Button {inp[1]}"
    if inp[0] == "axis":
        return f"Axis {inp[1]} {'+' if inp[2] > 0 else '−'}"
    if inp[0] == "hat":
        return f"Hat {inp[1]} {inp[2]}"
    return str(inp)


# ── GUI ───────────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PES6 Settings+  —  enhanced settings.exe for Pro Evolution Soccer 6")
        self.configure(bg=BG)
        self.minsize(860, 500)
        self.geometry("1100x700")

        self._dat_path    = tk.StringVar(value=str(DEFAULT_DAT))
        self._presets_dir = tk.StringVar(value=str(DEFAULT_PRESETS_DIR))
        self._status      = tk.StringVar(value="Ready.")
        self._controllers: list[dict] = []
        self._preset_files: list[Path] = []
        self._ctrl_var = tk.IntVar(value=-1)
        self._ctrl_radios: list[tk.Radiobutton] = []
        self._slot_vars: dict[str, tk.StringVar] = {}   # guid_hex → "None"/"Player N"
        self._extra_ctrls: list[dict] = []              # connected pads not in .dat

        # Display / Online tab state
        self._scrmode_var  = tk.StringVar(value=SCREEN_MODES[0])
        self._res_var      = tk.StringVar(value="")
        self._quality_var  = tk.StringVar(value=QUALITY_LEVELS[0])
        self._bright_var   = tk.IntVar(value=BRIGHTNESS_DEFAULT)
        self._udpauto_var  = tk.BooleanVar(value=True)
        self._port_var     = tk.StringVar(value=str(DEFAULT_UDP_PORT))
        self._upnp_var     = tk.BooleanVar(value=True)
        self._display_modes: list[tuple[int, int]] = []

        self._build_ui()
        self._try_autoload()

    def _btn(self, parent, text, cmd, w=None, accent=False):
        cfg = dict(text=text, command=cmd, relief="flat", cursor="hand2",
                   bg=BG2, fg=FG, activebackground=BG3, activeforeground=FG,
                   font=("Segoe UI", 9), padx=6, pady=4)
        if accent:
            cfg.update(bg=GRN, fg="#1e1e2e", activebackground="#94e2d5",
                       font=("Segoe UI", 10, "bold"), pady=8)
        if w:
            cfg["width"] = w
        return tk.Button(parent, **cfg)

    def _frame(self, parent, title):
        return tk.LabelFrame(parent, text=f" {title} ", bg=BG, fg=ACC,
                             font=("Segoe UI", 9, "bold"), bd=1, relief="groove")

    def _build_ui(self):
        # Shared settings.dat path bar (applies to all tabs)
        top = self._frame(self, "settings.dat location")
        top.pack(fill="x", padx=8, pady=(8, 0))
        top.columnconfigure(1, weight=1)

        tk.Label(top, text="File:", bg=BG, fg=FG,
                 font=("Segoe UI", 9)).grid(row=0, column=0, padx=(8,4), pady=5, sticky="w")
        tk.Entry(top, textvariable=self._dat_path, bg=BG2, fg=FG,
                 insertbackground=FG, relief="flat", font=("Segoe UI", 9)
                 ).grid(row=0, column=1, padx=4, pady=5, sticky="ew")
        self._btn(top, "…", self._browse_dat, w=3).grid(row=0, column=2, padx=2)
        self._btn(top, "↺ Reload", self._reload_all).grid(row=0, column=3, padx=(2,8))

        # Tabs: Display / Device / Online
        style = ttk.Style()
        try:
            style.theme_use("default")
        except tk.TclError:
            pass
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=BG2, foreground=FG2,
                        padding=(16, 7), font=("Segoe UI", 9, "bold"), borderwidth=0)
        style.map("TNotebook.Tab",
                  background=[("selected", BG3)], foreground=[("selected", ACC)])

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=(8, 0))

        display_tab = tk.Frame(nb, bg=BG)
        device_tab  = tk.Frame(nb, bg=BG)
        online_tab  = tk.Frame(nb, bg=BG)
        nb.add(display_tab, text="  Display  ")
        nb.add(device_tab,  text="  Device  ")
        nb.add(online_tab,  text="  Online  ")

        self._build_display_tab(display_tab)
        self._build_device_tab(device_tab)
        self._build_online_tab(online_tab)

        tk.Label(self, textvariable=self._status, bg="#181825", fg=FG2,
                 font=("Segoe UI", 8), anchor="w").pack(fill="x", ipady=3)

    # ── Display tab ─────────────────────────────────────────────────────────────

    def _build_display_tab(self, parent):
        f = self._frame(parent, "Display")
        f.pack(fill="x", padx=8, pady=8)
        f.columnconfigure(1, weight=1)

        def row(r, text):
            tk.Label(f, text=text, bg=BG, fg=FG, font=("Segoe UI", 9),
                     anchor="w").grid(row=r, column=0, padx=(12,8), pady=8, sticky="w")

        # Screen Mode
        row(0, "Screen Mode")
        self._scrmode_cb = ttk.Combobox(f, textvariable=self._scrmode_var,
                                        values=SCREEN_MODES, state="readonly",
                                        font=("Segoe UI", 9), width=18)
        self._scrmode_cb.grid(row=0, column=1, padx=(0,12), pady=8, sticky="w")
        if not SCREENMODE_VERIFIED:
            self._scrmode_cb.configure(state="disabled")
            tk.Label(f, text="⚠ pending Window/Full-Screen diff to confirm byte 0x08",
                     bg=BG, fg=YEL, font=("Segoe UI", 8, "italic"), anchor="w"
                     ).grid(row=1, column=1, padx=(0,12), pady=(0,4), sticky="w")

        # Resolution
        row(2, "Resolution")
        self._res_cb = ttk.Combobox(f, textvariable=self._res_var, state="readonly",
                                    font=("Segoe UI", 9), width=18)
        self._res_cb.grid(row=2, column=1, padx=(0,12), pady=8, sticky="w")

        # Quality
        row(3, "Quality")
        self._quality_cb = ttk.Combobox(f, textvariable=self._quality_var,
                                        values=QUALITY_LEVELS, state="readonly",
                                        font=("Segoe UI", 9), width=18)
        self._quality_cb.grid(row=3, column=1, padx=(0,12), pady=8, sticky="w")

        # Brightness
        row(4, "Brightness")
        bf = tk.Frame(f, bg=BG)
        bf.grid(row=4, column=1, padx=(0,12), pady=8, sticky="ew")
        tk.Label(bf, text="Dark", bg=BG, fg=FG2,
                 font=("Segoe UI", 8)).pack(side="left")
        tk.Scale(bf, from_=BRIGHTNESS_MIN, to=BRIGHTNESS_MAX, orient="horizontal",
                 variable=self._bright_var, bg=BG, fg=FG, troughcolor=BG2,
                 highlightthickness=0, showvalue=True, length=200,
                 activebackground=ACC).pack(side="left", padx=6)
        tk.Label(bf, text="Bright", bg=BG, fg=FG2,
                 font=("Segoe UI", 8)).pack(side="left")

        self._btn(parent, "💾   Save Display settings", self._save_display,
                  accent=True).pack(fill="x", padx=8, pady=(0,8))

    # ── Device tab ──────────────────────────────────────────────────────────────

    def _build_device_tab(self, device_tab):
        pf = self._frame(device_tab, "Presets folder")
        pf.pack(fill="x", padx=8, pady=(8,0))
        pf.columnconfigure(1, weight=1)
        tk.Label(pf, text="Folder:", bg=BG, fg=FG,
                 font=("Segoe UI", 9)).grid(row=0, column=0, padx=(8,4), pady=5, sticky="w")
        tk.Entry(pf, textvariable=self._presets_dir, bg=BG2, fg=FG,
                 insertbackground=FG, relief="flat", font=("Segoe UI", 9)
                 ).grid(row=0, column=1, padx=4, pady=5, sticky="ew")
        self._btn(pf, "…", self._browse_presets_dir, w=3).grid(row=0, column=2, padx=(2,8))

        main = tk.Frame(device_tab, bg=BG)
        main.pack(fill="both", expand=True, padx=8, pady=8)
        main.columnconfigure(0, weight=0)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        left = tk.Frame(main, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0,6))
        left.rowconfigure(1, weight=1)

        cf = self._frame(left, "Controllers  →  assign to a Player slot")
        cf.grid(row=0, column=0, sticky="ew", pady=(0,6))
        self._ctrl_container = tk.Frame(cf, bg=BG)
        self._ctrl_container.pack(fill="x")
        self._no_ctrl_lbl = tk.Label(self._ctrl_container, text="(no data)",
                                     bg=BG, fg=FG2, font=("Segoe UI", 9, "italic"))
        self._no_ctrl_lbl.pack(padx=12, pady=6)
        self._btn(cf, "✔  Apply assignments", self._apply_assignments, accent=True
                  ).pack(fill="x", padx=8, pady=(2,6))

        mf = self._frame(left, "Selected Controller Mapping")
        mf.grid(row=1, column=0, sticky="nsew")
        mf.rowconfigure(0, weight=1)
        mf.columnconfigure(0, weight=1)

        canvas = tk.Canvas(mf, bg=BG, highlightthickness=0, width=260)
        vsb = tk.Scrollbar(mf, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        inner = tk.Frame(canvas, bg=BG)
        cw = canvas.create_window((0,0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: (
            canvas.configure(scrollregion=canvas.bbox("all")),
            canvas.itemconfig(cw, width=canvas.winfo_width())))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(cw, width=e.width))
        canvas.bind_all("<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        tk.Label(inner, text="PES 6 Action", bg=BG, fg=ACC,
                 font=("Segoe UI", 9, "bold"), anchor="w", width=20
                 ).grid(row=0, column=0, padx=(8,4), pady=(4,2), sticky="w")
        tk.Label(inner, text="ID", bg=BG, fg=ACC,
                 font=("Segoe UI", 9, "bold"), width=5
                 ).grid(row=0, column=1, padx=2, pady=(4,2))
        tk.Label(inner, text="Bind", bg=BG, fg=ACC,
                 font=("Segoe UI", 9, "bold"), width=4
                 ).grid(row=0, column=2, padx=(2,8), pady=(4,2))

        self._mapping_vars: list[tk.StringVar] = []
        self._mapping_entries: list[tk.Entry] = []
        for i, name in enumerate(PES_INPUTS):
            tk.Label(inner, text=name, bg=BG, fg=FG,
                     font=("Segoe UI", 9), anchor="w", width=20
                     ).grid(row=i+1, column=0, padx=(8,4), pady=1, sticky="w")
            var = tk.StringVar(value="—")
            ent = tk.Entry(inner, textvariable=var, bg=BG2, fg=GRN, width=5,
                           justify="center", relief="flat", insertbackground=FG,
                           font=("Segoe UI", 9))
            ent.grid(row=i+1, column=1, padx=2, pady=1)
            bb = tk.Button(inner, text="🎮", command=lambda idx=i: self._bind_action(idx),
                           relief="flat", cursor="hand2", bg=BG3, fg=FG,
                           activebackground=ACC, font=("Segoe UI", 8), padx=2, pady=0)
            bb.grid(row=i+1, column=2, padx=(2,8), pady=1)
            self._mapping_vars.append(var)
            self._mapping_entries.append(ent)

        self._btn(mf, "💾  Save mapping to selected controller",
                  self._save_mapping).grid(row=1, column=0, columnspan=2,
                                           padx=8, pady=(2,6), sticky="ew")

        right = self._frame(main, "Saved Presets")
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        right.columnconfigure(1, weight=1)

        self._preset_list = tk.Listbox(
            right, bg=BG2, fg=FG, selectbackground=ACC,
            selectforeground="#1e1e2e", font=("Segoe UI", 9),
            relief="flat", activestyle="none", borderwidth=0, highlightthickness=0)
        self._preset_list.grid(row=0, column=0, columnspan=2,
                               padx=8, pady=(8,4), sticky="nsew")
        self._preset_list.bind("<<ListboxSelect>>", self._on_preset_select)

        self._detail_lbl = tk.Label(right, text="", bg=BG, fg=FG2,
                                    font=("Segoe UI", 8), anchor="w")
        self._detail_lbl.grid(row=1, column=0, columnspan=2, padx=8, pady=(0,4), sticky="w")

        self._btn(right, "✅  Apply selected preset to selected controller",
                  self._apply_preset, accent=True).grid(
                      row=2, column=0, columnspan=2, padx=8, pady=(4,3), sticky="ew")
        self._btn(right, "⭐  Set as default for this controller type",
                  self._set_preset_default).grid(
                      row=3, column=0, columnspan=2, padx=8, pady=3, sticky="ew")
        self._btn(right, "💾  Save preset for selected controller",
                  self._save_preset).grid(row=4, column=0, columnspan=2,
                                          padx=8, pady=3, sticky="ew")
        self._btn(right, "📥  Import preset from file",
                  self._import_preset).grid(row=5, column=0, columnspan=2,
                                            padx=8, pady=3, sticky="ew")
        self._btn(right, "🗑  Delete",
                  self._delete_preset).grid(row=6, column=0,
                                            padx=(8,3), pady=(3,8), sticky="ew")
        self._btn(right, "📂  Open folder",
                  self._open_presets_folder).grid(row=6, column=1,
                                                  padx=(3,8), pady=(3,8), sticky="ew")

    # ── Online tab ──────────────────────────────────────────────────────────────

    def _build_online_tab(self, parent):
        f = self._frame(parent, "Online")
        f.pack(fill="x", padx=8, pady=8)
        f.columnconfigure(1, weight=1)

        tk.Checkbutton(f, text="Auto-select UDP port", variable=self._udpauto_var,
                       command=self._on_udpauto_toggle, bg=BG, fg=FG,
                       selectcolor=BG2, activebackground=BG, activeforeground=ACC,
                       font=("Segoe UI", 9), anchor="w"
                       ).grid(row=0, column=0, columnspan=2, padx=12, pady=(10,4), sticky="w")

        tk.Label(f, text="Port (udp)", bg=BG, fg=FG, font=("Segoe UI", 9),
                 anchor="w").grid(row=1, column=0, padx=(12,8), pady=8, sticky="w")
        self._port_entry = tk.Entry(f, textvariable=self._port_var, bg=BG2, fg=FG,
                                    insertbackground=FG, relief="flat",
                                    font=("Segoe UI", 9), width=12)
        self._port_entry.grid(row=1, column=1, padx=(0,12), pady=8, sticky="w")
        tk.Label(f, text=f"(default: {DEFAULT_UDP_PORT})", bg=BG, fg=FG2,
                 font=("Segoe UI", 8, "italic")).grid(row=2, column=1, padx=(0,12),
                                                      pady=(0,4), sticky="w")

        tk.Checkbutton(f, text="Enable UPnP", variable=self._upnp_var, bg=BG, fg=FG,
                       selectcolor=BG2, activebackground=BG, activeforeground=ACC,
                       font=("Segoe UI", 9), anchor="w"
                       ).grid(row=3, column=0, columnspan=2, padx=12, pady=(8,10), sticky="w")

        self._btn(parent, "💾   Save Online settings", self._save_online,
                  accent=True).pack(fill="x", padx=8, pady=(0,8))

    def _on_udpauto_toggle(self):
        if self._udpauto_var.get():
            self._port_var.set(str(DEFAULT_UDP_PORT))
            self._port_entry.configure(state="disabled")
        else:
            self._port_entry.configure(state="normal")

    # ── controller list ───────────────────────────────────────────────────────

    def _instance_suffix(self, guid_hex: str) -> str:
        """ ' - N' to disambiguate identical controllers, matching settings.exe's
        numbering (first instance unsuffixed). Uses DirectInput enumeration order."""
        vp = lookup_vid_pid(guid_hex)
        guids = (_vid_pid_guids or {}).get(vp, [])
        if guid_hex in guids and len(guids) > 1:
            idx = guids.index(guid_hex)
            if idx > 0:
                return f" - {idx + 1}"
        return ""

    def _ctrl_display_name(self, c: dict) -> str:
        if c["is_keyboard"]:
            return "  ⌨  Keyboard (system)"
        name = (c.get("device_name", "") or c["guid_str"]) + self._instance_suffix(c["guid_hex"])
        if c.get("is_extra"):
            return f"  🎮  {name}  (not in file)"
        return f"  🎮  {name}"

    def _build_extra_ctrls(self) -> list[dict]:
        """Connected gamepads seen by pygame whose DInput GUID is known but is not
        in the .dat. Returned as controller-like dicts (is_extra=True) so they can
        appear in the assignment list and be assigned to a slot."""
        in_dat = {c["guid_hex"] for c in self._controllers}
        live_vps = {sdl_guid_vidpid(j.get_guid()) for j in open_joysticks()}
        live_vps.discard("")
        _ensure_cache()
        out, seen = [], set()
        idx = 1000
        for vp in sorted(live_vps):
            for ghex in (_vid_pid_guids or {}).get(vp, []):
                if ghex in in_dat or ghex in seen or not is_guid_connected(ghex):
                    continue
                seen.add(ghex)
                out.append({
                    "index": idx, "is_extra": True, "is_keyboard": False,
                    "connected": True, "active": False, "guid_hex": ghex,
                    "guid_str": _guid_str(bytes.fromhex(ghex)),
                    "model_family": _model_family(ghex),
                    "device_name": lookup_device_name(ghex),
                    "mapping": [UNASSIGNED] * MAPPING_SIZE,
                })
                idx += 1
        return out

    def _all_rows(self) -> list[dict]:
        """One row per distinct device: keyboard, then each controller GUID once
        (first block; 'active' = any block of that GUID is active), then connected
        pads not in the file. De-duping keeps the one-pad-per-player UI clean even
        if the file has duplicate blocks from settings.exe pad-reuse."""
        active_guids = {c["guid_hex"] for c in self._controllers if c.get("active")}
        rows, seen = [], set()
        for c in self._controllers:
            if c["guid_hex"] in seen:
                continue
            seen.add(c["guid_hex"])
            rows.append({**c, "active": c["guid_hex"] in active_guids})
        return rows + list(self._extra_ctrls)

    def _rebuild_ctrl_radios(self):
        for r in self._ctrl_radios:
            r.destroy()
        self._ctrl_radios.clear()
        self._no_ctrl_lbl.pack_forget()

        rows = self._all_rows()
        if not rows:
            self._no_ctrl_lbl.pack(padx=12, pady=6)
            return

        # Controllers occupy Player 1..8 (the keyboard is a separate device).
        SLOTS = ["None"] + [f"Player {i}" for i in range(1, MAX_PLAYERS + 1)]
        self._slot_vars = {}

        # Current slot = block position among controller blocks. Every controller
        # block IS a player (None deletes the block), so the player number follows
        # block order regardless of the (settings.exe-managed) active flag.
        infile_nonkb = [c for c in rows
                        if not c["is_keyboard"] and not c.get("is_extra")]
        slot_of = {c["guid_hex"]: i + 1 for i, c in enumerate(infile_nonkb)}

        for c in rows:
            row = tk.Frame(self._ctrl_container, bg=BG)
            row.pack(fill="x", padx=4, pady=1)
            self._ctrl_radios.append(row)

            dot = GRN if c["connected"] else RED
            tk.Label(row, text="●", bg=BG, fg=dot,
                     font=("Segoe UI", 8)).pack(side="left", padx=(2, 2))

            rb = tk.Radiobutton(
                row, text=self._ctrl_display_name(c).strip(),
                variable=self._ctrl_var, value=c["index"],
                command=self._on_ctrl_change,
                bg=BG, fg=YEL if c["is_keyboard"] else FG,
                selectcolor=BG2, activebackground=BG, activeforeground=ACC,
                font=("Segoe UI", 9, "italic" if c["is_keyboard"] else "normal"),
                anchor="w")
            rb.pack(side="left", anchor="w")

            if c["is_keyboard"]:
                tk.Label(row, text="(separate)", bg=BG, fg=FG2,
                         font=("Segoe UI", 8, "italic")).pack(side="right", padx=(4, 8))
            else:
                default = f"Player {slot_of[c['guid_hex']]}" if c["guid_hex"] in slot_of else "None"
                var = tk.StringVar(value=default)
                self._slot_vars[c["guid_hex"]] = var
                cb = ttk.Combobox(row, textvariable=var, values=SLOTS, state="readonly",
                                  width=9, font=("Segoe UI", 8))
                cb.pack(side="right", padx=(4, 6))
                cb.bind("<<ComboboxSelected>>",
                        lambda e, g=c["guid_hex"]: self._on_slot_change(g))

        # Track current slot values so we can swap when a taken slot is picked.
        self._prev_slots = {g: v.get() for g, v in self._slot_vars.items()}

        # Restore the previously selected controller if it's still present;
        # otherwise default to the first connected gamepad.
        want = getattr(self, "_desired_sel_guid", None)
        keep = next((c for c in rows if c["guid_hex"] == want), None) if want else None
        if keep:
            self._ctrl_var.set(keep["index"])
        else:
            connected = [c for c in rows if c["connected"] and not c["is_keyboard"]]
            self._ctrl_var.set((connected[0] if connected else rows[0])["index"])

    def _on_slot_change(self, guid_hex: str):
        """When a controller takes a slot already used by another, swap them so a
        slot is never double-assigned."""
        new_v = self._slot_vars[guid_hex].get()
        old_v = self._prev_slots.get(guid_hex, "None")
        if new_v != "None":
            for g, var in self._slot_vars.items():
                if g != guid_hex and var.get() == new_v:
                    var.set(old_v)               # other pad inherits this one's old slot
                    self._prev_slots[g] = old_v
                    break
        self._prev_slots[guid_hex] = new_v

    def _apply_assignments(self):
        p = Path(self._dat_path.get())
        if not p.exists() or not self._slot_vars:
            messagebox.showwarning("Assignments", "Load a settings.dat first.")
            return

        # Collect (guid, slot) from the dropdowns.
        chosen = []
        for ghex, var in self._slot_vars.items():
            v = var.get()
            if v != "None":
                chosen.append((ghex, int(v.split()[-1])))
        slots = [s for _, s in chosen]
        if len(slots) != len(set(slots)):
            messagebox.showwarning("Assignments",
                                   "Two controllers share the same Player slot.")
            return

        # Type-default presets for NEWLY assigned pads only (was inactive / not
        # in file before, now assigned a slot).
        was_active = {c["guid_hex"] for c in self._controllers if c.get("active")}
        presets_dir = Path(self._presets_dir.get())
        presets: dict[str, list[int]] = {}
        for ghex, _slot in chosen:
            if ghex not in was_active:
                mp = type_default_mapping(presets_dir, lookup_vid_pid(ghex))
                if mp:
                    presets[ghex] = mp

        if not messagebox.askyesno(
                "Apply assignments",
                "Set Player slots from these dropdowns?\n\n"
                "Assigned pads become active players (in slot order); the rest "
                "stay registered but inactive. A backup will be saved."):
            return
        try:
            self._make_backup(p)
            set_player_assignments(p, chosen, presets)
            self._load_from_dat()
            applied = ", ".join(f"P{s}" for s in sorted(slots)) or "none"
            extra = f"  ({len(presets)} got type-default preset)" if presets else ""
            self._status_set(f"Assignments applied: {applied}.{extra}")
        except Exception as e:
            self._status_set(f"Error applying assignments: {e}", True)

    def _set_preset_default(self):
        sel = self._preset_list.curselection()
        if not sel or sel[0] >= len(self._preset_files):
            messagebox.showinfo("Set default", "Select a preset from the list.")
            return
        f = self._preset_files[sel[0]]
        try:
            obj = load_preset(f)
        except Exception as e:
            self._status_set(f"Error: {e}", True)
            return
        vp = obj.get("vid_pid", "")
        if not vp:
            messagebox.showwarning(
                "Set default",
                "This preset has no controller type (VID/PID) recorded.\n\n"
                "Re-save it from a connected controller so the type is captured.")
            return
        presets_dir = Path(self._presets_dir.get())
        # Clear the flag on any other preset of the same type, set it on this one.
        for g in sorted(presets_dir.glob(f"*{PRESET_EXT}")):
            try:
                o = load_preset(g)
            except Exception:
                continue
            if o.get("vid_pid") == vp and o.get("default_for_type"):
                o["default_for_type"] = False
                g.write_text(json.dumps(o, indent=2, ensure_ascii=False),
                             encoding="utf-8")
        obj["default_for_type"] = True
        f.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
        self._refresh_preset_list()
        self._status_set(f"'{obj.get('name')}' is now the default for {vp}.")

    def _on_ctrl_change(self, *_):
        c = self._selected_ctrl()
        if c:
            self._show_mapping(c["mapping"])
            self._refresh_preset_list()

    def _show_mapping(self, mapping: list):
        c = self._selected_ctrl()
        locked = bool(c and (c["is_keyboard"] or c.get("is_extra")))
        for i, var in enumerate(self._mapping_vars):
            b = mapping[i] if i < len(mapping) else UNASSIGNED
            var.set("—" if b == UNASSIGNED else str(b))
            self._mapping_entries[i].config(fg=FG2 if b == UNASSIGNED else GRN,
                                            state="disabled" if locked else "normal")

    def _read_mapping_from_ui(self) -> list[int]:
        out = []
        for var in self._mapping_vars:
            t = var.get().strip()
            if t in ("", "—"):
                out.append(UNASSIGNED)
            else:
                v = int(t)
                if not (0 <= v <= 255):
                    raise ValueError(f"ID {v} out of range (0–255).")
                out.append(v)
        return out

    def _save_mapping(self):
        ctrl = self._selected_ctrl()
        if not ctrl:
            messagebox.showwarning("No data", "Select a controller first.")
            return
        if ctrl["is_keyboard"]:
            messagebox.showwarning("Keyboard", "Cannot modify the system keyboard.")
            return
        if ctrl.get("is_extra"):
            messagebox.showinfo("Not assigned yet",
                                "Assign this controller to a Player slot and click "
                                "'Apply assignments' first, then edit its mapping.")
            return
        p = Path(self._dat_path.get())
        if not p.exists():
            messagebox.showerror("Error", f"File not found:\n{p}")
            return
        try:
            mapping = self._read_mapping_from_ui()
        except ValueError as e:
            messagebox.showwarning("Invalid value", str(e))
            return
        try:
            self._make_backup(p)
            write_mapping(p, ctrl["index"], mapping)
            self._load_from_dat()
            self._status_set(f"Mapping saved to Controller {ctrl['index']}.")
        except Exception as e:
            self._status_set(f"Error saving mapping: {e}", True)

    def _find_joysticks_for(self, ctrl: dict):
        """Return ALL connected pygame joysticks matching this controller's model
        (by VID/PID). Identical pads share button numbering, so capturing from any
        of them gives the right value — no fragile per-instance guessing."""
        js = open_joysticks()
        if not js:
            return [], "No controllers detected by pygame."
        vp = lookup_vid_pid(ctrl["guid_hex"])
        matches = [j for j in js if sdl_guid_vidpid(j.get_guid()) == vp] if vp else []
        if matches:
            return matches, ""
        # VID/PID didn't resolve — fall back to all connected pads.
        return js, ""

    def _bind_action(self, action_idx: int):
        ctrl = self._selected_ctrl()
        if not ctrl or ctrl["is_keyboard"]:
            messagebox.showwarning("Bind", "Select a game controller first.")
            return
        if ctrl.get("is_extra"):
            messagebox.showinfo("Not assigned yet",
                                "Assign this controller to a Player slot and click "
                                "'Apply assignments' first, then bind its buttons.")
            return
        if _ensure_pygame() is None:
            messagebox.showerror(
                "pygame missing",
                "Live capture needs pygame-ce.\n\nInstall with:\n"
                "    python -m pip install pygame-ce")
            return
        joys, err = self._find_joysticks_for(ctrl)
        if not joys:
            messagebox.showwarning("Bind", err)
            return

        dlg = tk.Toplevel(self)
        dlg.title(f"Bind  {PES_INPUTS[action_idx]}")
        dlg.configure(bg=BG)
        dlg.transient(self)
        dlg.grab_set()
        dlg.geometry("360x180")

        tk.Label(dlg, text=f"Press the control for:\n{PES_INPUTS[action_idx]}",
                 bg=BG, fg=ACC, font=("Segoe UI", 11, "bold"),
                 justify="center").pack(pady=(18, 6))
        raw_var = tk.StringVar(value="Waiting for input…")
        tk.Label(dlg, textvariable=raw_var, bg=BG, fg=FG,
                 font=("Segoe UI", 10)).pack(pady=2)
        tk.Label(dlg, text="(buttons auto-fill the ID; verify axes/hats in-game)",
                 bg=BG, fg=FG2, font=("Segoe UI", 8, "italic")).pack(pady=2)

        state = {"done": False}

        def finish(value=None, raw=""):
            state["done"] = True
            if value is not None:
                self._mapping_vars[action_idx].set(str(value))
                self._mapping_entries[action_idx].config(fg=GRN)
                self._status_set(f"{PES_INPUTS[action_idx]} ← {raw} (ID {value})")
            try:
                dlg.grab_release(); dlg.destroy()
            except tk.TclError:
                pass

        # flush any queued events first
        if _pygame:
            _pygame.event.clear()

        def tick():
            if state["done"]:
                return
            inp = poll_input_event(joys)
            if inp:
                raw_var.set(describe_input(inp))
                if inp[0] == "button":
                    finish(inp[1], describe_input(inp))
                    return
                # Axis/hat (e.g. L2/R2 triggers): PES's axis/POV ID can't be
                # derived from pygame, so close instead of looping and ask the
                # user to type the ID. (Defaults already cover the triggers.)
                state["done"] = True
                self._status_set(
                    f"{PES_INPUTS[action_idx]}: detected {describe_input(inp)} — "
                    f"enter its ID manually (analog axes can't be auto-bound).")
                try:
                    dlg.grab_release(); dlg.destroy()
                except tk.TclError:
                    pass
                return
            dlg.after(40, tick)

        tk.Button(dlg, text="Cancel", command=lambda: finish(None),
                  relief="flat", bg=BG2, fg=FG, activebackground=BG3,
                  cursor="hand2", padx=10, pady=4).pack(pady=8)
        dlg.bind("<Escape>", lambda e: finish(None))
        dlg.after(40, tick)

    def _selected_ctrl(self) -> dict | None:
        idx = self._ctrl_var.get()
        return next((c for c in self._all_rows() if c["index"] == idx), None)

    # ── dat actions ───────────────────────────────────────────────────────────

    def _try_autoload(self):
        # Populate resolution dropdown from the live display modes (once).
        self._display_modes = list_display_modes()
        self._res_cb.configure(
            values=[f"{w} x {h}" for (w, h) in self._display_modes])
        # Ship working defaults for common pads so users don't have to make any.
        seed_builtin_presets(Path(self._presets_dir.get()))
        if Path(self._dat_path.get()).exists():
            self._reload_all()
        else:
            self._refresh_preset_list()

    def _reload_all(self):
        self._load_from_dat()
        self._load_settings_fields()

    def _browse_dat(self):
        p = filedialog.askopenfilename(
            title="Select settings.dat",
            filetypes=[("DAT", "*.dat"), ("All files", "*.*")])
        if p:
            self._dat_path.set(p)
            self._reload_all()

    def _browse_presets_dir(self):
        d = filedialog.askdirectory(title="Presets folder")
        if d:
            self._presets_dir.set(d)
            self._refresh_preset_list()

    def _load_from_dat(self):
        p = Path(self._dat_path.get())
        if not p.exists():
            self._status_set(f"File not found: {p}", True)
            return
        try:
            prev = self._selected_ctrl()
            self._desired_sel_guid = prev["guid_hex"] if prev else None
            self._controllers = parse_dat(p)
            self._extra_ctrls = self._build_extra_ctrls()
            self._rebuild_ctrl_radios()
            self._on_ctrl_change()
            nkb = sum(1 for c in self._controllers if not c["is_keyboard"] and c["connected"])
            self._status_set(f"Loaded — {nkb} controller(s) connected")
        except Exception as e:
            self._controllers = []
            self._rebuild_ctrl_radios()
            self._status_set(str(e), True)

    def _make_backup(self, dat_path: Path) -> Path:
        # Single compat backup next to the file…
        backup = dat_path.with_name(BACKUP_NAME)
        shutil.copy2(dat_path, backup)
        # …plus a timestamped rolling backup so history can't be wiped.
        try:
            bdir = dat_path.with_name(dat_path.name + ".backups")
            bdir.mkdir(exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.copy2(dat_path, bdir / f"{dat_path.stem}-{stamp}.dat")
            snaps = sorted(bdir.glob(f"{dat_path.stem}-*.dat"))
            for old in snaps[:-20]:        # keep most recent 20
                old.unlink(missing_ok=True)
        except Exception:
            pass
        return backup

    # ── Display / Online load + save ───────────────────────────────────────────

    def _load_settings_fields(self):
        p = Path(self._dat_path.get())
        if not p.exists():
            return
        try:
            s = parse_settings(p)
        except Exception as e:
            self._status_set(f"Display/Online: {e}", True)
            return

        # Screen mode
        if 0 <= s["screenmode"] < len(SCREEN_MODES):
            self._scrmode_var.set(SCREEN_MODES[s["screenmode"]])
        # Resolution — add the current mode to the list if Windows didn't report it
        res_str = f"{s['width']} x {s['height']}"
        cur = list(self._res_cb.cget("values"))
        if res_str not in cur:
            cur.append(res_str)
            try:
                cur.sort(key=lambda v: tuple(int(x) for x in v.split(" x ")))
            except Exception:
                pass
            self._res_cb.configure(values=cur)
        self._res_var.set(res_str)
        # Quality
        if 0 <= s["quality"] < len(QUALITY_LEVELS):
            self._quality_var.set(QUALITY_LEVELS[s["quality"]])
        # Brightness
        self._bright_var.set(max(BRIGHTNESS_MIN, min(BRIGHTNESS_MAX, s["brightness"])))
        # Online
        self._udpauto_var.set(bool(s["udp_auto"]))
        self._port_var.set(str(s["udp_port"]))
        self._upnp_var.set(bool(s["upnp"]))
        self._on_udpauto_toggle()

    def _save_display(self):
        p = Path(self._dat_path.get())
        if not p.exists():
            messagebox.showerror("Error", f"File not found:\n{p}")
            return
        try:
            w, h = (int(x) for x in self._res_var.get().split(" x "))
        except Exception:
            messagebox.showwarning("Resolution", "Select a valid resolution first.")
            return
        fields = dict(
            width=w, height=h,
            quality=QUALITY_LEVELS.index(self._quality_var.get()),
            brightness=self._bright_var.get(),
        )
        if SCREENMODE_VERIFIED:
            fields["screenmode"] = SCREEN_MODES.index(self._scrmode_var.get())
        try:
            self._make_backup(p)
            write_settings(p, **fields)
            self._load_settings_fields()
            self._status_set(
                f"Display saved — {w}x{h}, {self._quality_var.get()}, "
                f"brightness {self._bright_var.get()}")
        except Exception as e:
            self._status_set(f"Error saving display: {e}", True)

    def _save_online(self):
        p = Path(self._dat_path.get())
        if not p.exists():
            messagebox.showerror("Error", f"File not found:\n{p}")
            return
        auto = self._udpauto_var.get()
        port = DEFAULT_UDP_PORT
        if not auto:
            try:
                port = int(self._port_var.get())
                if not (0 < port < 65536):
                    raise ValueError
            except ValueError:
                messagebox.showwarning("Port", "Enter a port between 1 and 65535.")
                return
        try:
            self._make_backup(p)
            write_settings(p, udp_auto=1 if auto else 0,
                           upnp=1 if self._upnp_var.get() else 0,
                           udp_port=port)
            self._load_settings_fields()
            self._status_set(
                f"Online saved — port {'auto' if auto else port}, "
                f"UPnP {'on' if self._upnp_var.get() else 'off'}")
        except Exception as e:
            self._status_set(f"Error saving online: {e}", True)

    # ── preset actions ────────────────────────────────────────────────────────

    def _save_preset(self):
        ctrl = self._selected_ctrl()
        if not ctrl:
            messagebox.showwarning("No data", "Load settings.dat first.")
            return
        if ctrl["is_keyboard"]:
            messagebox.showwarning("Keyboard", "Cannot save presets for keyboard.")
            return
        if ctrl.get("is_extra"):
            messagebox.showinfo("Not assigned yet",
                                "Assign this controller to a Player slot and apply "
                                "first, then save a preset from its mapping.")
            return
        dev_name = ctrl.get("device_name", "")
        name = simpledialog.askstring(
            "Preset name", "Name for this preset:", parent=self)
        if not name:
            return
        hint = simpledialog.askstring(
            "Controller model", "Controller name/model:",
            parent=self, initialvalue=dev_name) or dev_name
        presets_dir = Path(self._presets_dir.get())
        presets_dir.mkdir(parents=True, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in name)
        try:
            save_preset(presets_dir / f"{safe}{PRESET_EXT}",
                        name, ctrl["mapping"], hint, ctrl["model_family"],
                        vid_pid=lookup_vid_pid(ctrl["guid_hex"]))
            self._refresh_preset_list()
            self._status_set(f"Preset '{name}' saved.")
        except Exception as e:
            self._status_set(f"Error saving: {e}", True)

    def _preset_is_compatible(self, preset_obj: dict, ctrl: dict) -> bool:
        hint = (preset_obj.get("controller_hint") or "").strip().lower()
        dev  = (ctrl.get("device_name") or "").strip().lower()
        if hint and dev:
            return hint == dev
        # fallback: model_family (unreliable — all gamepads are f111)
        pf = preset_obj.get("model_family", "")
        if not pf:
            return True
        return pf == ctrl.get("model_family", "")

    def _refresh_preset_list(self):
        self._preset_list.delete(0, tk.END)
        self._preset_files = []
        ctrl = self._selected_ctrl()
        presets_dir = Path(self._presets_dir.get())
        if not presets_dir.exists():
            return
        for f in sorted(presets_dir.glob(f"*{PRESET_EXT}")):
            try:
                obj   = load_preset(f)
                label = obj.get("name", f.stem)
                hint  = obj.get("controller_hint", "")
                if hint:
                    label += f"  [{hint}]"
                if obj.get("default_for_type"):
                    label = f"⭐ {label}"
                if ctrl and not ctrl["is_keyboard"] and not self._preset_is_compatible(obj, ctrl):
                    label = f"⚠ {label}  ← different model"
                self._preset_list.insert(tk.END, label)
            except Exception:
                self._preset_list.insert(tk.END, f"⚠ {f.name}")
            self._preset_files.append(f)

    def _on_preset_select(self, _=None):
        sel = self._preset_list.curselection()
        if not sel or sel[0] >= len(self._preset_files):
            return
        try:
            obj   = load_preset(self._preset_files[sel[0]])
            ctrl  = self._selected_ctrl()
            compat = self._preset_is_compatible(obj, ctrl) if ctrl else True
            detail = (f"Controller: {obj.get('controller_hint') or '—'}    "
                      f"Created: {obj.get('created','—')}")
            if not compat:
                detail += "\n⚠ Preset from a different model — applying may break the config."
            self._detail_lbl.config(text=detail, fg=RED if not compat else FG2)
        except Exception:
            self._detail_lbl.config(text="", fg=FG2)

    def _apply_preset(self):
        sel = self._preset_list.curselection()
        if not sel:
            messagebox.showinfo("No selection", "Select a preset from the list.")
            return
        ctrl = self._selected_ctrl()
        if not ctrl:
            messagebox.showerror("No controller", "Select a controller first.")
            return
        if ctrl["is_keyboard"]:
            messagebox.showwarning("Keyboard", "Cannot apply presets to keyboard.")
            return
        if ctrl.get("is_extra"):
            messagebox.showinfo("Not assigned yet",
                                "Assign this controller to a Player slot and apply "
                                "first, then apply a preset to it.")
            return
        dat_path = Path(self._dat_path.get())
        if not dat_path.exists():
            messagebox.showerror("Error", f"File not found:\n{dat_path}")
            return
        try:
            obj  = load_preset(self._preset_files[sel[0]])
            name = obj.get("name", "?")
            num  = ctrl["index"]

            if not self._preset_is_compatible(obj, ctrl):
                hint_preset = obj.get("controller_hint") or "another model"
                if not messagebox.askyesno("⚠ Different models",
                        f"Preset '{name}' was created for '{hint_preset}'.\n\n"
                        f"Applying it to a different controller model may cause "
                        f"PES 6 to reset the entire configuration.\n\n"
                        f"Apply anyway?", icon="warning"):
                    return

            if not messagebox.askyesno("Confirm",
                    f"Apply preset '{name}' to Controller {num}?\n\n"
                    f"File: {dat_path}\n\n"
                    f"A backup will be saved ({BACKUP_NAME})."):
                return

            backup = self._make_backup(dat_path)
            write_mapping(dat_path, num, obj["mapping"])
            self._load_from_dat()
            self._status_set(
                f"Preset '{name}' applied to Controller {num}. Backup: {backup.name}")
        except Exception as e:
            self._status_set(f"Error applying: {e}", True)

    def _import_preset(self):
        p = filedialog.askopenfilename(
            title="Import preset",
            filetypes=[(f"PES6 Preset (*{PRESET_EXT})", f"*{PRESET_EXT}"),
                       ("All files", "*.*")])
        if not p:
            return
        presets_dir = Path(self._presets_dir.get())
        presets_dir.mkdir(parents=True, exist_ok=True)
        try:
            load_preset(Path(p))
            shutil.copy2(p, presets_dir / Path(p).name)
            self._refresh_preset_list()
            self._status_set(f"Preset imported: {Path(p).name}")
        except Exception as e:
            self._status_set(f"Error importing: {e}", True)

    def _delete_preset(self):
        sel = self._preset_list.curselection()
        if not sel:
            return
        if messagebox.askyesno("Delete", f"Delete:\n{self._preset_list.get(sel[0])}?"):
            try:
                self._preset_files[sel[0]].unlink()
                self._refresh_preset_list()
                self._detail_lbl.config(text="", fg=FG2)
                self._status_set("Preset deleted.")
            except Exception as e:
                self._status_set(f"Error: {e}", True)

    def _open_presets_folder(self):
        d = Path(self._presets_dir.get())
        d.mkdir(parents=True, exist_ok=True)
        os.startfile(str(d))

    def _status_set(self, msg: str, err: bool = False):
        self._status.set(("❌ " if err else "✔ ") + msg)


if __name__ == "__main__":
    App().mainloop()
