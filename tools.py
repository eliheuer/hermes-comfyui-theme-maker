"""Tool implementations: list canonical palette keys, generate mood
images, extract dominant palette colors, write/apply/render themes
in the canonical ComfyUI palette JSON format.
"""

import copy
import json
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import token_inventory as inventory


_VALID_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _err(msg, **extra):
    payload = {"error": msg}
    payload.update(extra)
    return json.dumps(payload)


def _missing_dep_error(pkg):
    return _err(
        f"{pkg} is not installed in hermes-agent's venv. From a shell, run:\n"
        f"  ~/.hermes/hermes-agent/venv/bin/pip install -r requirements.txt\n"
        f"(Use the full path — running plain `pip install` will install into "
        f"the wrong Python.)"
    )


def _comfy_url():
    return os.environ.get(
        "HERMES_COMFYUI_API_URL", "http://127.0.0.1:8188"
    ).rstrip("/")


def _cache_dir():
    raw = os.environ.get(
        "HERMES_COMFYUI_CACHE_DIR", "~/.cache/hermes-comfyui-theme-maker",
    )
    d = Path(raw).expanduser()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _theme_path(name):
    return _cache_dir() / f"{name}.json"


# --- ComfyUI HTTP helpers (used by image gen + settings API) -------------

def _http_post(path, body, timeout=30):
    req = urllib.request.Request(
        _comfy_url() + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _http_get_bytes(path, timeout=30):
    with urllib.request.urlopen(_comfy_url() + path, timeout=timeout) as r:
        return r.read()


def _http_get_json(path, timeout=30):
    raw = _http_get_bytes(path, timeout)
    if not raw:
        return None
    return json.loads(raw)


# --- list canonical palette keys ----------------------------------------

def list_comfyui_tokens(args, **kwargs):
    group = (args or {}).get("group", "all")
    groups = inventory.all_groups()
    if group == "all":
        return json.dumps({
            "node_slot": list(groups["node_slot"]),
            "litegraph_base": list(groups["litegraph_base"]),
            "comfy_base_required": list(inventory.COMFY_BASE_REQUIRED_KEYS),
            "comfy_base_optional": list(inventory.COMFY_BASE_OPTIONAL_KEYS),
            "total_keys": (
                len(groups["node_slot"])
                + len(groups["litegraph_base"])
                + len(groups["comfy_base"])
            ),
        })
    if group not in groups:
        return _err(f"unknown group: {group!r}",
                    valid_groups=["all", *groups.keys()])
    return json.dumps({group: list(groups[group])})


# --- write theme: validate + save palette JSON to cache -----------------

def _validate_palette(palette):
    if not isinstance(palette, dict):
        return "palette must be an object"
    if "id" not in palette or not isinstance(palette["id"], str):
        return "palette.id is required (string)"
    if not _VALID_SLUG.match(palette["id"]):
        return f"palette.id must match {_VALID_SLUG.pattern!r}"
    if "name" not in palette or not isinstance(palette["name"], str):
        return "palette.name is required (string)"
    if "colors" not in palette or not isinstance(palette["colors"], dict):
        return "palette.colors is required (object)"
    colors = palette["colors"]
    for group_name in ("node_slot", "litegraph_base", "comfy_base"):
        if group_name not in colors:
            return f"palette.colors.{group_name} is required (may be {{}})"
        if not isinstance(colors[group_name], dict):
            return f"palette.colors.{group_name} must be an object"

    valid_keys = inventory.all_groups()
    for group_name, keys in colors.items():
        for key in keys:
            if group_name in valid_keys and key not in valid_keys[group_name]:
                return (
                    f"unknown key in {group_name}: {key!r} "
                    f"(see list_comfyui_tokens)"
                )
    return None


def write_comfyui_theme(args, **kwargs):
    args = args or {}
    palette = args.get("palette")
    err = _validate_palette(palette)
    if err:
        return _err(err)

    name = palette["id"]
    out = _theme_path(name)
    try:
        out.write_text(json.dumps(palette, indent=2))
    except OSError as e:
        return _err(f"write failed: {e}")

    counts = {
        g: len(palette["colors"].get(g, {}))
        for g in ("node_slot", "litegraph_base", "comfy_base")
    }
    return json.dumps({
        "ok": True,
        "id": name,
        "path": str(out),
        "overrides": counts,
    })


# --- apply theme: register via ComfyUI settings API + activate -----------

def apply_comfyui_theme(args, **kwargs):
    args = args or {}
    name = (args.get("name") or "").strip()
    if not _VALID_SLUG.match(name):
        return _err(f"invalid theme id: {name!r}")
    theme_file = _theme_path(name)
    if not theme_file.exists():
        return _err(
            f"theme not found in cache: {theme_file}. "
            "Call write_comfyui_theme first."
        )
    try:
        palette = json.loads(theme_file.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return _err(f"could not read theme JSON: {e}")

    try:
        existing = _http_get_json(
            "/api/settings/Comfy.CustomColorPalettes"
        ) or {}
    except (urllib.error.URLError, OSError) as e:
        return _err(
            f"ComfyUI not reachable at {_comfy_url()}: {e}. "
            "Start ComfyUI and try again."
        )
    if not isinstance(existing, dict):
        existing = {}
    existing[palette["id"]] = palette

    try:
        _http_post("/api/settings/Comfy.CustomColorPalettes", existing)
        _http_post("/api/settings/Comfy.ColorPalette", palette["id"])
    except (urllib.error.URLError, OSError) as e:
        return _err(f"settings POST failed: {e}")

    return json.dumps({
        "ok": True,
        "id": palette["id"],
        "active": True,
        "registered_count": len(existing),
        "note": (
            "Theme registered as a custom palette and set active. "
            "If the theme menu still shows the previous palette, "
            "open Settings → Appearance and toggle palettes once — "
            "ComfyUI's frontend hydrates customs at GraphCanvas mount, "
            "so a fresh page load picks them up automatically."
        ),
    })


# --- ComfyUI image generation (unchanged from previous version) ---------

_QUALITY_PREFIX = "masterpiece, best quality, score_7, safe, anime, "
_DEFAULT_NEGATIVE = (
    "worst quality, low quality, score_1, score_2, score_3, "
    "blurry, jpeg artifacts, sepia"
)

_ANIMA_WORKFLOW = {
    "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "anima-preview.safetensors", "weight_dtype": "default"}},
    "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_06b_base.safetensors", "type": "stable_diffusion", "device": "default"}},
    "3": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
    "4": {"class_type": "LoraLoader", "inputs": {"model": ["1", 0], "clip": ["2", 0], "lora_name": "anima-turbo-lora-v0.1.safetensors", "strength_model": 0.9, "strength_clip": 0.9}},
    "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 1], "text": ""}},
    "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 1], "text": _DEFAULT_NEGATIVE}},
    "7": {"class_type": "EmptyLatentImage", "inputs": {"width": 768, "height": 768, "batch_size": 1}},
    "8": {"class_type": "KSampler", "inputs": {"model": ["4", 0], "positive": ["5", 0], "negative": ["6", 0], "latent_image": ["7", 0], "seed": 0, "steps": 8, "cfg": 1.0, "sampler_name": "er_sde", "scheduler": "simple", "denoise": 1.0}},
    "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
    "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": "hermes-mood"}},
}

_COMFY_TIMEOUT = 90
_MAX_SIZE = 1024
_MIN_SIZE = 256


def _build_workflow(prompt, size, seed):
    wf = copy.deepcopy(_ANIMA_WORKFLOW)
    wf["5"]["inputs"]["text"] = _QUALITY_PREFIX + prompt
    wf["7"]["inputs"]["width"] = size
    wf["7"]["inputs"]["height"] = size
    wf["8"]["inputs"]["seed"] = seed
    return wf


def generate_mood_image(args, **kwargs):
    args = args or {}
    prompt = (args.get("prompt") or "").strip()
    if not prompt:
        return _err("prompt is required")
    size = int(args.get("size") or 768)
    if not (_MIN_SIZE <= size <= _MAX_SIZE):
        return _err(f"size must be between {_MIN_SIZE} and {_MAX_SIZE}")
    seed = args.get("seed")
    if seed is None:
        seed = random.randint(1, 2**31 - 1)
    seed = int(seed)

    started = time.time()
    workflow = _build_workflow(prompt, size, seed)
    try:
        submission = json.loads(_http_post(
            "/prompt",
            {"prompt": workflow, "client_id": "hermes-comfyui-theme-maker"},
        ))
    except (urllib.error.URLError, OSError) as e:
        return _err(f"ComfyUI not reachable at {_comfy_url()}: {e}")

    if submission.get("node_errors"):
        return _err("ComfyUI rejected the workflow",
                    node_errors=submission["node_errors"])
    prompt_id = submission.get("prompt_id")
    if not prompt_id:
        return _err("ComfyUI did not return a prompt_id", raw=submission)

    deadline = started + _COMFY_TIMEOUT
    image_ref = None
    while time.time() < deadline:
        try:
            history = _http_get_json(f"/history/{prompt_id}")
        except (urllib.error.URLError, OSError) as e:
            return _err(f"history poll failed: {e}")
        record = (history or {}).get(prompt_id)
        if record and record.get("status", {}).get("completed"):
            for _node_id, output in (record.get("outputs") or {}).items():
                images = output.get("images") or []
                if images:
                    image_ref = images[0]
                    break
            break
        time.sleep(0.5)

    if image_ref is None:
        return _err(f"timeout after {_COMFY_TIMEOUT}s with no output image")

    qs = urllib.parse.urlencode({
        "filename": image_ref["filename"],
        "type": image_ref.get("type", "output"),
        "subfolder": image_ref.get("subfolder", ""),
    })
    try:
        data = _http_get_bytes(f"/view?{qs}")
    except (urllib.error.URLError, OSError) as e:
        return _err(f"failed to fetch image: {e}")

    out = _cache_dir() / f"{prompt_id}.png"
    try:
        out.write_bytes(data)
    except OSError as e:
        return _err(f"failed to cache image: {e}")

    return json.dumps({
        "ok": True,
        "path": str(out),
        "prompt_id": prompt_id,
        "seed": seed,
        "size": size,
        "elapsed_seconds": round(time.time() - started, 2),
    })


# --- palette extraction --------------------------------------------------

def extract_palette_from_image(args, **kwargs):
    args = args or {}
    raw_path = args.get("path") or ""
    n_colors = int(args.get("n_colors") or 8)
    if not raw_path:
        return _err("path is required")
    if not (1 <= n_colors <= 32):
        return _err("n_colors must be 1-32")

    try:
        from PIL import Image
    except ImportError:
        return _missing_dep_error("Pillow")

    path = Path(raw_path).expanduser()
    if not path.exists():
        return _err(f"image not found: {path}")
    try:
        img = Image.open(path).convert("RGB")
    except Exception as e:
        return _err(f"could not open image: {e}")

    img.thumbnail((256, 256))
    quant = img.quantize(colors=n_colors, method=Image.Quantize.MEDIANCUT)
    palette = quant.getpalette() or []
    raw_counts = quant.getcolors(maxcolors=n_colors * 4) or []

    rows = []
    for count, idx in raw_counts:
        if idx * 3 + 2 >= len(palette):
            continue
        r = palette[idx * 3]
        g = palette[idx * 3 + 1]
        b = palette[idx * 3 + 2]
        rows.append((count, f"#{r:02x}{g:02x}{b:02x}"))
    rows.sort(reverse=True)
    rows = rows[:n_colors]
    total = sum(c for c, _ in rows) or 1
    colors = [{"hex": h, "percent": round(100 * c / total, 1)} for c, h in rows]
    return json.dumps({"ok": True, "colors": colors, "source": str(path)})


# --- swatch + image rendering --------------------------------------------

def _hex_rgb01(hex_value):
    return (
        int(hex_value[1:3], 16) / 255.0,
        int(hex_value[3:5], 16) / 255.0,
        int(hex_value[5:7], 16) / 255.0,
    )


def _hex_luminance(hex_value):
    r, g, b = _hex_rgb01(hex_value)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _ansi_swatch(hex_value, width=4):
    r = int(hex_value[1:3], 16)
    g = int(hex_value[3:5], 16)
    b = int(hex_value[5:7], 16)
    return f"\033[48;2;{r};{g};{b}m{' ' * width}\033[0m"


def _load_palette(name):
    theme_file = _theme_path(name)
    if not theme_file.exists():
        return None, _err(f"theme not found in cache: {theme_file}")
    try:
        return json.loads(theme_file.read_text()), None
    except (OSError, json.JSONDecodeError) as e:
        return None, _err(f"could not read theme JSON: {e}")


_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def _format_token_line(key, value, override):
    """Format one token line in the swatch.

    `override=True` → token IS in the theme (show colored block + value).
    `override=False` → token is INHERITED from default (show muted name).
    """
    desc = inventory.KEY_DESCRIPTIONS.get(key, "")
    if not override:
        return (
            f"  {_DIM}    ·                       "
            f"{key:<35}{desc}{_RESET}"
        )
    if isinstance(value, str) and _HEX_RE.match(value):
        return (
            f"  {_ansi_swatch(value)}  {value}  "
            f"{key:<35}{_DIM}{desc}{_RESET}"
        )
    # Non-hex value (e.g. rgba(...) for bar-shadow, base64 PNG, enum int).
    truncated = str(value)
    if len(truncated) > 22:
        truncated = truncated[:19] + "..."
    return (
        f"  {_DIM}    ·{_RESET}  {truncated:<22}  "
        f"{key:<35}{_DIM}{desc}{_RESET}"
    )


def _render_group_with_roles(group_name, items, role_buckets):
    """Render one schema group, partitioned into role buckets."""
    lines = []
    overridden_keys = set(items.keys())
    bucket_keys = {k for _, keys in role_buckets for k in keys}
    # Tokens that are present but don't fit any documented bucket
    # — show under "Other" to keep them visible.
    extras = sorted(k for k in overridden_keys if k not in bucket_keys)

    for label, keys in role_buckets:
        present = [k for k in keys if k in overridden_keys]
        absent = [k for k in keys if k not in overridden_keys]
        if not present and not absent:
            continue
        lines.append(f"  {_BOLD}{label}{_RESET}")
        for key in present:
            lines.append(_format_token_line(key, items[key], override=True))
        for key in absent:
            lines.append(_format_token_line(key, None, override=False))
        lines.append("")

    if extras:
        lines.append(f"  {_BOLD}Other (not in role buckets){_RESET}")
        for key in extras:
            lines.append(_format_token_line(key, items[key], override=True))
        lines.append("")
    return lines


def render_theme_swatch(args, **kwargs):
    args = args or {}
    name = (args.get("name") or "").strip()
    if not _VALID_SLUG.match(name):
        return _err(f"invalid theme id: {name!r}")
    palette, err = _load_palette(name)
    if err:
        return err

    colors = palette.get("colors") or {}
    cb = colors.get("comfy_base") or {}
    lg = colors.get("litegraph_base") or {}
    ns = colors.get("node_slot") or {}
    total = len(cb) + len(lg) + len(ns)
    light = palette.get("light_theme")
    flag = "light" if light else ("dark" if light is False else "no flag")

    n_cb_total = len(inventory.COMFY_BASE_KEYS)
    n_lg_total = len(inventory.LITEGRAPH_BASE_KEYS)
    n_ns_total = len(inventory.NODE_SLOT_KEYS)

    lines = [
        "",
        f"  {_BOLD}{palette.get('name') or palette['id']}{_RESET}"
        f"  {_DIM}· {flag} theme · {total} overrides{_RESET}",
        "",
        f"  {_DIM}Coverage: "
        f"comfy_base {len(cb)}/{n_cb_total}  ·  "
        f"litegraph_base {len(lg)}/{n_lg_total}  ·  "
        f"node_slot {len(ns)}/{n_ns_total}{_RESET}",
        f"  {_DIM}Tokens not overridden inherit from "
        f"DEFAULT_{'LIGHT' if light else 'DARK'}_COLOR_PALETTE.{_RESET}",
        "",
    ]

    # Comfy base — UI chrome, role-grouped
    if cb:
        lines.append(f"  {_BOLD}╭── COMFY BASE — UI chrome ──{_RESET}")
        lines.append("")
        lines.extend(
            _render_group_with_roles("comfy_base", cb,
                                     inventory.COMFY_BASE_ROLES)
        )

    # LiteGraph base — canvas, role-grouped
    if lg:
        lines.append(f"  {_BOLD}╭── LITEGRAPH — canvas ──{_RESET}")
        lines.append("")
        lines.extend(
            _render_group_with_roles("litegraph_base", lg,
                                     inventory.LITEGRAPH_BASE_ROLES)
        )

    # Node slot — connection types (one row per type, no role-grouping)
    if ns:
        lines.append(f"  {_BOLD}╭── NODE SLOT — connection types ──{_RESET}")
        lines.append("")
        for key in inventory.NODE_SLOT_KEYS:
            present = key in ns
            value = ns.get(key)
            lines.append(_format_token_line(key, value, present))
        lines.append("")
    elif total > 0:
        lines.append(
            f"  {_DIM}Node slot connection-type colors all inherited "
            f"from default ({n_ns_total} keys: CLIP, MODEL, IMAGE, "
            f"LATENT, ...).{_RESET}"
        )
        lines.append("")

    return json.dumps({
        "ok": True,
        "id": palette["id"],
        "tokens_in_theme": total,
        "swatch": "\n".join(lines),
    })


_IMAGE_BG = "#0e0e10"
_IMAGE_FG = "#f0eee6"
_IMAGE_MUTED = "#8a8a92"
_IMAGE_SIZE = 1080
_IMAGE_MARGIN = 60


def render_theme_image(args, **kwargs):
    args = args or {}
    name = (args.get("name") or "").strip()
    if not _VALID_SLUG.match(name):
        return _err(f"invalid theme id: {name!r}")
    palette, err = _load_palette(name)
    if err:
        return err

    try:
        import drawbot_skia.drawbot as db
    except ImportError:
        return _missing_dep_error("drawbot-skia")

    raw_output = (args.get("output_path") or "").strip()
    if raw_output:
        out_path = Path(raw_output).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        out_path = _cache_dir() / f"{name}.png"

    colors = palette.get("colors") or {}

    def hex_items(group):
        return sorted(
            (k, v)
            for k, v in (colors.get(group) or {}).items()
            if isinstance(v, str) and _HEX_RE.match(v)
        )

    sections = [(group, hex_items(group)) for group in _GROUP_ORDER]
    total = sum(len(items) for _g, items in sections)

    def yflip(y_top):
        return _IMAGE_SIZE - y_top

    def fill_hex(hex_value):
        r, g, b = _hex_rgb01(hex_value)
        db.fill(r, g, b)

    def rect_top(x, y_top, w, h):
        db.rect(x, yflip(y_top + h), w, h)

    def text_top(text, x, y_top_baseline, fontname="Helvetica", size=20):
        db.font(fontname)
        db.fontSize(size)
        db.text(text, (x, yflip(y_top_baseline)))

    def draw_swatch(x, y_top, w, h, hex_val, label):
        fill_hex(hex_val)
        rect_top(x, y_top, w, h)
        text_color = "#0a0a0a" if _hex_luminance(hex_val) > 0.55 else "#f5f5f5"
        fill_hex(text_color)
        text_top(hex_val, x + 14, y_top + 30, "Helvetica-Bold", 20)
        text_top(label, x + 14, y_top + 52, "Helvetica", 14)

    def draw_section(title, items, y_top, cols=4, swatch_h=78, gutter=14):
        if not items:
            return y_top
        fill_hex(_IMAGE_FG)
        text_top(title, _IMAGE_MARGIN, y_top + 18, "Helvetica-Bold", 20)
        y_grid = y_top + 36
        inner = _IMAGE_SIZE - _IMAGE_MARGIN * 2
        swatch_w = (inner - gutter * (cols - 1)) // cols
        for i, (key, hex_val) in enumerate(items):
            col = i % cols
            row = i // cols
            sx = _IMAGE_MARGIN + col * (swatch_w + gutter)
            sy = y_grid + row * (swatch_h + gutter)
            draw_swatch(sx, sy, swatch_w, swatch_h, hex_val, key)
        rows = (len(items) + cols - 1) // cols
        return y_grid + rows * (swatch_h + gutter) + 18

    db.newDrawing()
    db.size(_IMAGE_SIZE, _IMAGE_SIZE)
    fill_hex(_IMAGE_BG)
    db.rect(0, 0, _IMAGE_SIZE, _IMAGE_SIZE)

    fill_hex(_IMAGE_FG)
    text_top(palette.get("name") or palette["id"], _IMAGE_MARGIN, 90,
             "Helvetica-Bold", 56)
    fill_hex(_IMAGE_MUTED)
    light = palette.get("light_theme")
    flag = "light" if light else ("dark" if light is False else "")
    suffix = f"{flag} · " if flag else ""
    text_top(
        f"{suffix}{total} overrides · hermes-comfyui-theme-maker",
        _IMAGE_MARGIN, 125, "Helvetica", 18,
    )

    y = 160
    for title, items in sections:
        y = draw_section(_GROUP_LABELS[title], items, y)

    fill_hex(_IMAGE_MUTED)
    text_top(
        "github.com/eliheuer/hermes-comfyui-theme-maker · GPL-3.0",
        _IMAGE_MARGIN, _IMAGE_SIZE - 36, "Helvetica", 14,
    )

    try:
        db.saveImage(str(out_path))
    finally:
        db.endDrawing()

    return json.dumps({
        "ok": True,
        "id": palette["id"],
        "path": str(out_path),
        "size": f"{_IMAGE_SIZE}x{_IMAGE_SIZE}",
        "tokens_in_theme": total,
    })
