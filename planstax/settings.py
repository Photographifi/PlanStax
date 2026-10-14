"""Processing parameters, JSON presets and import of RegiStax 6 setting files."""

from __future__ import annotations

import configparser
import json
import os
import re
import shutil
from dataclasses import asdict, dataclass, field, fields, is_dataclass

from . import APP_NAME


@dataclass
class AlignSettings:
    mode: str = "auto"            # "auto" | "planet" | "surface"
    ap_spacing: int = 30          # distance between alignment points (px)
    ap_box_size: int = 35         # size of the box matched around each point (px)
    search_radius: int = 10       # max local displacement searched (px)
    min_brightness: int = 30      # points darker than this (0-255) are dropped
    max_brightness: int = 255     # points brighter than this (0-255) are dropped
    edge_margin: int = 20         # no points closer than this to the frame edge
    max_points: int = 500
    min_structure: float = 0.05   # drop points with less detail than 5 % of the best one
    reference_frames: int = 0     # frames averaged into the reference (0 = automatic)
    quality_noise: float = 1.5    # noise robustness of the quality estimator (blur sigma)


@dataclass
class LimitSettings:
    method: str = "percent"       # "percent" | "count" | "quality"
    percent: float = 80.0
    count: int = 100
    min_quality: float = 50.0     # in % of the best frame's quality


@dataclass
class StackSettings:
    local_percent: float = 100.0  # best frames kept for each alignment point (% of selection)
    scale: float = 1.0            # output resampling (1, 1.5, 2, 3)
    normalize_brightness: bool = False
    quality_weighting: bool = False


@dataclass
class WaveletLayer:
    enabled: bool = True
    gain: float = 1.0
    denoise: float = 0.0


def _default_layers() -> list[WaveletLayer]:
    return [WaveletLayer() for _ in range(6)]


@dataclass
class WaveletSettings:
    scheme: str = "b3spline"      # "b3spline" (à trous) | "gaussian"
    step: str = "dyadic"          # "dyadic" (1, 2, 4, 8…) | "linear" (1, 2, 3, 4…)
    initial: float = 1.0          # scale of the first layer
    target: str = "rgb"           # "rgb" | "luminance"
    layers: list[WaveletLayer] = field(default_factory=_default_layers)

    def is_neutral(self) -> bool:
        return all((not l.enabled) or (abs(l.gain - 1.0) < 1e-6 and l.denoise <= 0) for l in self.layers)


@dataclass
class PostSettings:
    shift_r: tuple[float, float] = (0.0, 0.0)
    shift_b: tuple[float, float] = (0.0, 0.0)
    gain_r: float = 1.0
    gain_g: float = 1.0
    gain_b: float = 1.0
    black: float = 0.0
    white: float = 1.0
    gamma: float = 1.0
    brightness: float = 0.0
    contrast: float = 1.0
    saturation: float = 1.0
    rotate: int = 0               # 0, 90, 180, 270 (clockwise)
    flip_h: bool = False
    flip_v: bool = False

    def is_neutral(self) -> bool:
        return self == PostSettings()


@dataclass
class Settings:
    align: AlignSettings = field(default_factory=AlignSettings)
    limit: LimitSettings = field(default_factory=LimitSettings)
    stack: StackSettings = field(default_factory=StackSettings)
    wavelet: WaveletSettings = field(default_factory=WaveletSettings)
    post: PostSettings = field(default_factory=PostSettings)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        return _from_dict(cls, data)

    def copy(self) -> "Settings":
        return Settings.from_dict(self.to_dict())


def _from_dict(cls, data):
    """Build a dataclass from a dict, ignoring unknown keys and keeping defaults for missing ones."""
    obj = cls()
    if not isinstance(data, dict):
        return obj
    for f in fields(cls):
        if f.name not in data:
            continue
        current = getattr(obj, f.name)
        value = data[f.name]
        if is_dataclass(current):
            value = _from_dict(type(current), value)
        elif f.name == "layers":
            layers = [_from_dict(WaveletLayer, v) for v in value][:6]
            value = layers + [WaveletLayer() for _ in range(6 - len(layers))]
        elif isinstance(current, tuple):
            value = tuple(float(v) for v in value)
        elif isinstance(current, bool):
            value = bool(value)
        elif isinstance(current, int):
            value = int(value)
        elif isinstance(current, float):
            value = float(value)
        setattr(obj, f.name, value)
    return obj


# ---------------------------------------------------------------- presets

FORMER_NAMES = ("PlanetStack",)  # earlier names of the program, whose settings are taken over


def config_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    path = os.path.join(base, APP_NAME)
    if not os.path.isdir(path):
        # First start under this name: take over the presets and settings of a former name
        # (copied, so the old folder stays as a backup).
        for old in FORMER_NAMES:
            former = os.path.join(base, old)
            if os.path.isdir(former):
                try:
                    shutil.copytree(former, path)
                except OSError:
                    pass
                break
    os.makedirs(path, exist_ok=True)
    return path


def presets_dir() -> str:
    path = os.path.join(config_dir(), "presets")
    os.makedirs(path, exist_ok=True)
    return path


def _preset_path(name: str) -> str:
    safe = re.sub(r'[<>:"/\\|?*]', "_", name).strip() or "sans-nom"
    return os.path.join(presets_dir(), safe + ".json")


def list_presets() -> list[str]:
    return sorted(os.path.splitext(f)[0] for f in os.listdir(presets_dir()) if f.endswith(".json"))


def save_preset(name: str, settings: Settings) -> str:
    path = _preset_path(name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(settings.to_dict(), fh, indent=2, ensure_ascii=False)
    return path


def load_preset(name_or_path: str) -> Settings:
    path = name_or_path if os.path.isfile(name_or_path) else _preset_path(name_or_path)
    with open(path, encoding="utf-8") as fh:
        return Settings.from_dict(json.load(fh))


def delete_preset(name: str) -> None:
    path = _preset_path(name)
    if os.path.isfile(path):
        os.remove(path)


# ---------------------------------------------------------------- RegiStax 6 import

def _read_text(path: str) -> str:
    """RegiStax (Delphi) writes .ini files in ANSI but macros in UTF-16: honour any BOM."""
    with open(path, "rb") as fh:
        raw = fh.read()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", "replace")
    return raw.decode("latin-1")


def _read_ini(path: str) -> dict[str, str]:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str.lower
    try:
        parser.read_string(_read_text(path))
    except (configparser.Error, OSError, UnicodeDecodeError):
        return {}
    values: dict[str, str] = {}
    for section in parser.sections():
        values.update(parser[section])
    return values


def _num(values: dict, key: str, default=None):
    raw = values.get(key.lower())
    if raw is None:
        return default
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return default


def registax_preset_names(folder: str) -> list[str]:
    """Names of the RegiStax 6 setting sets found in a folder (from `wavelet-NAME.ini` etc.)."""
    names = set()
    for f in os.listdir(folder):
        m = re.match(r"(?i)(estimate|align|limit|stack|wavelet|macro)-(.+)\.ini$", f)
        if m:
            names.add(m.group(2))
    return sorted(names)


def registax_folders(folder: str) -> list[str]:
    """RegiStax 6 writes its .ini files next to its executable; when installed under
    Program Files, Windows silently redirects those writes to the user's VirtualStore,
    which therefore holds the most recent copies. Returns [VirtualStore copy, folder]."""
    folders = [folder]
    local = os.environ.get("LOCALAPPDATA", "")
    _, rest = os.path.splitdrive(os.path.abspath(folder))
    virtual = os.path.join(local, "VirtualStore", rest.lstrip("\\/"))
    if local and os.path.isdir(virtual) and os.path.normcase(virtual) != os.path.normcase(folder):
        folders.insert(0, virtual)
    return folders


def import_all_registax(folder: str) -> list[str]:
    """Import every RegiStax 6 setting set found in folder (and its VirtualStore copy) as presets."""
    imported: list[str] = []
    for f in registax_folders(folder):
        for name in registax_preset_names(f):
            if name not in imported:
                save_preset(name, import_registax(f, name))
                imported.append(name)
    return imported


def import_registax(folder: str, name: str, base: Settings | None = None) -> Settings:
    """Build Settings from RegiStax 6 files `estimate-NAME.ini`, `limit-NAME.ini`,
    `wavelet-NAME.ini` (and `registax6.ini` for the box size).

    Alignment-point and selection values carry over directly. Wavelet *gains* do not:
    RegiStax's slider-to-strength formula is not public, and no simple conversion of the
    slider positions gives sensible results for all layers, so only the scheme is imported
    and gains stay neutral (see `registax_wavelet_positions`)."""
    s = (base or Settings()).copy()

    # A macro (macro-NAME.ini: "Estimate-Mak2", "Limit0-Mak2", "Wavelet-Mak3"…) says which
    # setting set each step really uses.
    sources: dict[str, str] = {}
    macro = os.path.join(folder, f"macro-{name}.ini")
    if os.path.isfile(macro):
        for line in _read_text(macro).splitlines():
            m = re.match(r"(?i)\s*(estimate|align|limit|stack|wavelet)\d*-(.+?)\s*$", line)
            if m:
                sources.setdefault(m.group(1).lower(), m.group(2))

    def ini(prefix: str) -> dict:
        path = os.path.join(folder, f"{prefix}-{sources.get(prefix, name)}.ini")
        return _read_ini(path) if os.path.isfile(path) else {}

    main = _read_ini(os.path.join(folder, "registax6.ini"))
    if (v := _num(main, "blocksize_Value")) is not None:
        s.align.ap_box_size = int(v)

    est = ini("estimate")
    if (v := _num(est, "Dist_Value")) is not None:
        s.align.ap_spacing = int(v)
    if (v := _num(est, "LowIntensity_Value")) is not None:
        s.align.min_brightness = int(v)
    if (v := _num(est, "HighIntensity_Value")) is not None:
        s.align.max_brightness = int(v)
    if (v := _num(est, "MatrixEdgesetting_Value")) is not None:
        s.align.edge_margin = int(v)
    if (v := _num(est, "NoOfPoints_Value")) is not None:
        s.align.max_points = int(v)

    lim = ini("limit")
    if (v := _num(lim, "LimitNoOfFrames_Value")) is not None:
        s.limit.method = "percent"
        s.limit.percent = float(min(100.0, max(1.0, v)))

    wav = ini("wavelet")
    if wav:
        scheme = _num(wav, "Waveletscheme_ItemIndex", 0)
        s.wavelet.scheme = "gaussian" if scheme == 1 else "b3spline"
    return s


_SLIDER_KEYS = ["Layer1Slider_Position", "Layer2slider_Position", "Layer3slider_Position",
                "layer4slider_Position", "Layer5slider_Position", "Layer6slider_Position"]


def registax_wavelet_positions(folder: str, name: str) -> list[int] | None:
    """The six RegiStax wavelet slider positions of a setting set (10 = neutral), for display."""
    for f in registax_folders(folder):
        path = os.path.join(f, f"wavelet-{name}.ini")
        if not os.path.isfile(path):
            continue
        wav = _read_ini(path)
        return [int(_num(wav, k, 10)) for k in _SLIDER_KEYS]
    return None
