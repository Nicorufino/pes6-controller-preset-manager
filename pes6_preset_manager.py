"""
PES 6 Controller Preset Manager
"""

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
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

HEADER_SIZE   = 16
BLOCK_SIZE    = 44
MAPPING_OFF   = 0x10
MAPPING_SIZE  = 24
FILE_SIZE     = 420
FOOTER_OFF    = 0x198
UNASSIGNED    = 0xFF
PRESET_EXT    = ".pes6preset"
BACKUP_NAME   = "settings.bak"
KEYBOARD_GUID = "612b1d6fa0d5cf11bfc7444553540000"
MODEL_FAMILY_OFF = 6
MODEL_FAMILY_LEN = 2

DEFAULT_DAT = (Path.home() / "Documents" / "KONAMI"
               / "Pro Evolution Soccer 6" / "settings.dat")

DEFAULT_PRESETS_DIR = Path.home() / "Documents" / "PES 6 Controller Presets"

BG, BG2, BG3 = "#1e1e2e", "#313244", "#45475a"
FG, FG2, ACC, GRN, YEL, RED = "#cdd6f4", "#a6adc8", "#89b4fa", "#a6e3a1", "#f9e2af", "#f38ba8"

# ── Nombres conocidos por VID&PID ─────────────────────────────────────────────
# Fuente: USB HID device list + conocimiento de la comunidad
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
    "VID_2DC8&PID_3106": "8BitDo Pro 2",
    "VID_2DC8&PID_3107": "8BitDo Ultimate",
    "VID_2DC8&PID_6001": "8BitDo SN30 Pro",
    "VID_0F0D&PID_00C1": "HORI Pad",
    "VID_0F0D&PID_0092": "HORI Fighting Commander",
    "VID_0738&PID_4726": "Mad Catz Xbox 360 Controller",
    "VID_1532&PID_0900": "Razer Onza",
    "VID_1532&PID_0A00": "Razer Sabertooth",
}

# ── Lookup guid → nombre y VID/PID via registro de Windows ───────────────────

_device_names:   dict[str, str] | None = None   # guid_hex → friendly name
_guid_vid_pid:   dict[str, str] | None = None   # guid_hex → "VID_XXXX&PID_XXXX"


def _build_name_cache() -> tuple[dict[str, str], dict[str, str]]:
    import re
    names:   dict[str, str] = {}
    vid_pids: dict[str, str] = {}
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

            vid_pid_clean = vid_pid.upper()
            if "VID&" in vid_pid_clean and "PID" in vid_pid_clean:
                m = re.search(r'VID&[0-9A-F]*?([0-9A-F]{4})_PID(?:&[0-9A-F]*?([0-9A-F]{4}))?',
                              vid_pid_clean)
                if m:
                    vid_pid_clean = f"VID_{m.group(1)}&PID_{m.group(2) or '0000'}"

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
                        winreg.CloseKey(idx_key)
                    except OSError:
                        pass
                winreg.CloseKey(cal_key)
            except OSError:
                pass

        winreg.CloseKey(root)
    except Exception:
        pass
    return names, vid_pids


def _ensure_cache() -> None:
    global _device_names, _guid_vid_pid
    if _device_names is None:
        _device_names, _guid_vid_pid = _build_name_cache()


def lookup_device_name(guid_hex: str) -> str:
    _ensure_cache()
    return (_device_names or {}).get(guid_hex, "")


def _get_connected_vid_pids() -> set[str]:
    """VID_XXXX&PID_XXXX strings for HID devices currently plugged in.
    Uses SetupDiGetClassDevs with DIGCF_PRESENT — only physically connected devices."""
    import re, ctypes
    result: set[str] = set()
    try:
        setupapi = ctypes.WinDLL("setupapi")

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                        ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]

        HID_GUID = GUID(0x4D1E55B2, 0xF16F, 0x11CF,
                        (ctypes.c_ubyte * 8)(0x88, 0xCB, 0x00, 0x11, 0x11, 0x00, 0x00, 0x30))

        DIGCF_PRESENT = 0x02
        DIGCF_DEVICEINTERFACE = 0x10
        INVALID_HANDLE = ctypes.c_void_p(-1).value

        hdev = setupapi.SetupDiGetClassDevsW(
            ctypes.byref(HID_GUID), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
        if hdev == INVALID_HANDLE:
            return result

        class SP_DEVINFO_DATA(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_ulong), ("ClassGuid", GUID),
                        ("DevInst", ctypes.c_ulong), ("Reserved", ctypes.c_ulong)]

        info = SP_DEVINFO_DATA()
        info.cbSize = ctypes.sizeof(info)
        buf = ctypes.create_unicode_buffer(512)
        i = 0
        while setupapi.SetupDiEnumDeviceInfo(hdev, i, ctypes.byref(info)):
            setupapi.SetupDiGetDeviceInstanceIdW(hdev, ctypes.byref(info), buf, 512, None)
            m = re.search(r'VID_([0-9A-F]{4})&PID_([0-9A-F]{4})', buf.value.upper())
            if m:
                result.add(f"VID_{m.group(1)}&PID_{m.group(2)}")
            i += 1

        setupapi.SetupDiDestroyDeviceInfoList(hdev)
    except Exception:
        pass
    return result


def is_guid_connected(guid_hex: str) -> bool:
    """Returns True if the physical device for this GUID is currently connected."""
    _ensure_cache()
    vp = (_guid_vid_pid or {}).get(guid_hex)
    if not vp:
        return False
    return vp in _get_connected_vid_pids()


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
    n = 0
    while True:
        bs = HEADER_SIZE + n * BLOCK_SIZE
        if bs + BLOCK_SIZE > FOOTER_OFF:
            break
        if data[bs + 0x0A : bs + 0x0E] != b'DEST':
            break
        guid    = data[bs : bs + 16]
        ghex    = guid.hex()
        mapping = list(data[bs + MAPPING_OFF : bs + MAPPING_OFF + MAPPING_SIZE])
        is_kb   = ghex == KEYBOARD_GUID
        result.append({
            "index":        n,
            "block_start":  bs,
            "guid_hex":     ghex,
            "guid_str":     _guid_str(guid),
            "model_family": _model_family(ghex),
            "device_name":  lookup_device_name(ghex),
            "mapping":      mapping,
            "is_keyboard":  is_kb,
            "connected":    is_kb or is_guid_connected(ghex),
        })
        n += 1
    return result


def _update_checksum(data: bytearray) -> None:
    csum = sum(data[4:]) & 0xFFFF
    data[2] = csum & 0xFF
    data[3] = (csum >> 8) & 0xFF


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
    path.write_bytes(bytes(data))


# ── preset I/O ───────────────────────────────────────────────────────────────

def save_preset(path: Path, name: str, mapping: list,
                hint: str = "", model_family: str = "") -> None:
    path.write_text(json.dumps({
        "name":            name,
        "controller_hint": hint,
        "model_family":    model_family,
        "created":         datetime.now().isoformat(timespec="seconds"),
        "mapping":         mapping,
        "labels":          PES_INPUTS,
    }, indent=2, ensure_ascii=False), encoding="utf-8")


def load_preset(path: Path) -> dict:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if "mapping" not in obj or len(obj["mapping"]) != MAPPING_SIZE:
        raise ValueError("Invalid preset or unsupported version.")
    return obj


# ── GUI ───────────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PES 6 Controller Preset Manager")
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
        top = self._frame(self, "Paths")
        top.pack(fill="x", padx=8, pady=(8, 0))
        top.columnconfigure(1, weight=1)

        tk.Label(top, text="settings.dat:", bg=BG, fg=FG,
                 font=("Segoe UI", 9)).grid(row=0, column=0, padx=(8,4), pady=5, sticky="w")
        tk.Entry(top, textvariable=self._dat_path, bg=BG2, fg=FG,
                 insertbackground=FG, relief="flat", font=("Segoe UI", 9)
                 ).grid(row=0, column=1, padx=4, pady=5, sticky="ew")
        self._btn(top, "…", self._browse_dat, w=3).grid(row=0, column=2, padx=2)
        self._btn(top, "↺ Reload", self._load_from_dat).grid(row=0, column=3, padx=(2,8))

        tk.Label(top, text="Presets folder:", bg=BG, fg=FG,
                 font=("Segoe UI", 9)).grid(row=1, column=0, padx=(8,4), pady=(0,5), sticky="w")
        tk.Entry(top, textvariable=self._presets_dir, bg=BG2, fg=FG,
                 insertbackground=FG, relief="flat", font=("Segoe UI", 9)
                 ).grid(row=1, column=1, padx=4, pady=(0,5), sticky="ew")
        self._btn(top, "…", self._browse_presets_dir, w=3).grid(row=1, column=2, padx=2, pady=(0,5))

        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True, padx=8, pady=8)
        main.columnconfigure(0, weight=0)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        left = tk.Frame(main, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0,6))
        left.rowconfigure(1, weight=1)

        cf = self._frame(left, "Detected Controllers")
        cf.grid(row=0, column=0, sticky="ew", pady=(0,6))
        self._ctrl_container = cf
        self._no_ctrl_lbl = tk.Label(cf, text="(no data)", bg=BG, fg=FG2,
                                     font=("Segoe UI", 9, "italic"))
        self._no_ctrl_lbl.pack(padx=12, pady=6)

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
                 font=("Segoe UI", 9, "bold"), anchor="w", width=22
                 ).grid(row=0, column=0, padx=(8,4), pady=(4,2), sticky="w")
        tk.Label(inner, text="Button", bg=BG, fg=ACC,
                 font=("Segoe UI", 9, "bold"), width=8
                 ).grid(row=0, column=1, padx=(4,8), pady=(4,2))

        self._mapping_labels: list[tk.Label] = []
        for i, name in enumerate(PES_INPUTS):
            tk.Label(inner, text=name, bg=BG, fg=FG,
                     font=("Segoe UI", 9), anchor="w", width=22
                     ).grid(row=i+1, column=0, padx=(8,4), pady=1, sticky="w")
            lbl = tk.Label(inner, text="—", bg=BG2, fg=FG2,
                           font=("Segoe UI", 9), width=8, anchor="center")
            lbl.grid(row=i+1, column=1, padx=(4,8), pady=1)
            self._mapping_labels.append(lbl)

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

        self._btn(right, "💾  Save preset for selected controller",
                  self._save_preset).grid(row=2, column=0, columnspan=2,
                                          padx=8, pady=(4,3), sticky="ew")
        self._btn(right, "📥  Import preset from file",
                  self._import_preset).grid(row=3, column=0, columnspan=2,
                                            padx=8, pady=3, sticky="ew")
        self._btn(right, "🗑  Delete",
                  self._delete_preset).grid(row=4, column=0,
                                            padx=(8,3), pady=(3,8), sticky="ew")
        self._btn(right, "📂  Open folder",
                  self._open_presets_folder).grid(row=4, column=1,
                                                  padx=(3,8), pady=(3,8), sticky="ew")

        self._btn(self, "✅   Apply selected preset to indicated controller",
                  self._apply_preset, accent=True
                  ).pack(fill="x", padx=8, pady=(0,4))

        tk.Label(self, textvariable=self._status, bg="#181825", fg=FG2,
                 font=("Segoe UI", 8), anchor="w").pack(fill="x", ipady=3)

    # ── controller list ───────────────────────────────────────────────────────

    def _ctrl_display_name(self, c: dict) -> str:
        if c["is_keyboard"]:
            return "  ⌨  Keyboard (system)"
        num  = c["index"]
        name = c.get("device_name", "")
        if name:
            return f"  🎮  Controller {num}  —  {name}"
        return f"  🎮  Controller {num}  —  {c['guid_str']}"

    def _rebuild_ctrl_radios(self):
        for r in self._ctrl_radios:
            r.destroy()
        self._ctrl_radios.clear()
        self._no_ctrl_lbl.pack_forget()

        if not self._controllers:
            self._no_ctrl_lbl.pack(padx=12, pady=6)
            return

        for c in self._controllers:
            if not c["connected"]:
                continue
            rb = tk.Radiobutton(
                self._ctrl_container,
                text=self._ctrl_display_name(c),
                variable=self._ctrl_var, value=c["index"],
                command=self._on_ctrl_change,
                bg=BG, fg=YEL if c["is_keyboard"] else FG,
                selectcolor=BG2, activebackground=BG, activeforeground=ACC,
                font=("Segoe UI", 9, "italic" if c["is_keyboard"] else "normal"))
            rb.pack(anchor="w", padx=6, pady=2)
            self._ctrl_radios.append(rb)

        connected = [c for c in self._controllers if c["connected"]]
        first = next((c for c in connected if not c["is_keyboard"]), None)
        if connected:
            self._ctrl_var.set((first or connected[0])["index"])

    def _on_ctrl_change(self, *_):
        idx = self._ctrl_var.get()
        c = next((c for c in self._controllers if c["index"] == idx), None)
        if c:
            self._show_mapping(c["mapping"])
            self._refresh_preset_list()

    def _show_mapping(self, mapping: list):
        for i, lbl in enumerate(self._mapping_labels):
            b = mapping[i] if i < len(mapping) else UNASSIGNED
            lbl.config(text="—" if b == UNASSIGNED else str(b),
                       fg=FG2 if b == UNASSIGNED else GRN)

    def _selected_ctrl(self) -> dict | None:
        idx = self._ctrl_var.get()
        return next((c for c in self._controllers if c["index"] == idx), None)

    # ── dat actions ───────────────────────────────────────────────────────────

    def _try_autoload(self):
        if Path(self._dat_path.get()).exists():
            self._load_from_dat()
        self._refresh_preset_list()

    def _browse_dat(self):
        p = filedialog.askopenfilename(
            title="Select controller settings.dat",
            filetypes=[("DAT", "*.dat"), ("All files", "*.*")])
        if p:
            self._dat_path.set(p)
            self._load_from_dat()

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
            self._controllers = parse_dat(p)
            self._rebuild_ctrl_radios()
            self._on_ctrl_change()
            nkb = sum(1 for c in self._controllers if not c["is_keyboard"] and c["connected"])
            self._status_set(f"Loaded — {nkb} controller(s) connected")
        except Exception as e:
            self._controllers = []
            self._rebuild_ctrl_radios()
            self._status_set(str(e), True)

    def _make_backup(self, dat_path: Path) -> Path:
        backup = dat_path.with_name(BACKUP_NAME)
        shutil.copy2(dat_path, backup)
        return backup

    # ── preset actions ────────────────────────────────────────────────────────

    def _save_preset(self):
        ctrl = self._selected_ctrl()
        if not ctrl:
            messagebox.showwarning("No data", "Load settings.dat first.")
            return
        if ctrl["is_keyboard"]:
            messagebox.showwarning("Keyboard", "Cannot save presets for keyboard.")
            return
        dev_name = ctrl.get("device_name", "")
        name = simpledialog.askstring(
            "Preset name",
            f"Name for Controller {ctrl['index']} preset:", parent=self)
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
                        name, ctrl["mapping"], hint, ctrl["model_family"])
            self._refresh_preset_list()
            self._status_set(f"Preset '{name}' saved.")
        except Exception as e:
            self._status_set(f"Error saving: {e}", True)

    def _preset_is_compatible(self, preset_obj: dict, ctrl: dict) -> bool:
        hint = (preset_obj.get("controller_hint") or "").strip().lower()
        dev  = (ctrl.get("device_name") or "").strip().lower()
        if hint and dev:
            return hint == dev
        # fallback: model_family (poco confiable — todos los gamepads son f111)
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
