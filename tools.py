"""Tool implementations: list/write/apply themes, generate mood images,
extract dominant palette colors, render swatches and infographics.
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
_SENTINEL_BEGIN = "/* hermes-comfyui-theme-maker:active */"
_SENTINEL_END = "/* hermes-comfyui-theme-maker:end */"
_DESIGN_SYSTEM_IMPORT = "@import '@comfyorg/design-system/css/style.css';"
_TOKEN_LINE_RE = re.compile(r"--([a-z][a-z0-9-]*):\s*(#[0-9a-fA-F]{6})")


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


def _resolve_frontend(raw):
    if not raw:
        return None, "frontend_path is required"
    path = Path(raw).expanduser().resolve()
    if not path.exists():
        return None, f"frontend_path does not exist: {path}"
    if not (path / "src" / "assets" / "css" / "style.css").exists():
        return None, (
            f"{path} does not look like a ComfyUI_frontend checkout "
            f"(missing src/assets/css/style.css)"
        )
    return path, None


def _themes_dir(frontend):
    d = frontend / "src" / "assets" / "css" / "themes"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _style_css(frontend):
    return frontend / "src" / "assets" / "css" / "style.css"


def _categorize_token(token):
    if token.startswith("color-charcoal-"):
        return "Charcoal (dark neutrals)"
    if token.startswith("color-smoke-"):
        return "Smoke (light neutrals)"
    if token.startswith("app-mode-"):
        return "App mode"
    if token.startswith("color-layout-"):
        return "Layout"
    if token.startswith("color-"):
        return "Accents"
    return "Other"


_CATEGORY_ORDER = [
    "Charcoal (dark neutrals)",
    "Smoke (light neutrals)",
    "Accents",
    "App mode",
    "Layout",
    "Other",
]


def _resolve_named_theme(args, require_exists=True):
    args = args or {}
    name = (args.get("name") or "").strip()
    raw_path = (args.get("frontend_path") or "").strip()
    if not _VALID_SLUG.match(name):
        return None, None, None, _err(f"invalid theme slug: {name!r}")
    frontend, err = _resolve_frontend(raw_path)
    if err:
        return None, None, None, _err(err)
    theme_file = _themes_dir(frontend) / f"{name}.css"
    if require_exists and not theme_file.exists():
        return None, None, None, _err(f"theme not found: {theme_file}")
    return name, frontend, theme_file, None


def _load_theme_groups(theme_file):
    matches = _TOKEN_LINE_RE.findall(theme_file.read_text())
    if not matches:
        return None, None, _err(f"no token overrides found in {theme_file}")
    groups = {}
    for token, hex_val in matches:
        groups.setdefault(_categorize_token(token), []).append(
            (token, hex_val.lower())
        )
    return matches, groups, None


def _render_css(name, overrides):
    body = "\n".join(f"  --{token}: {value};" for token, value in overrides.items())
    return f"/* hermes-comfyui-theme-maker: {name} */\n:root {{\n{body}\n}}\n"


# --- list / write / apply ------------------------------------------------

def list_tokens(args, **kwargs):
    layer = (args or {}).get("layer", "all")
    if layer == "all":
        rows = inventory.all_tokens()
    else:
        try:
            rows = [(n, d, desc, layer) for n, d, desc in inventory.by_layer(layer)]
        except KeyError:
            return _err(f"unknown layer: {layer!r}")
    payload = [
        {"name": n, "default": d, "description": desc, "layer": lyr}
        for n, d, desc, lyr in rows
    ]
    return json.dumps({"tokens": payload, "count": len(payload)})


def write_theme(args, **kwargs):
    name, frontend, theme_file, err = _resolve_named_theme(args, require_exists=False)
    if err:
        return err
    overrides = (args or {}).get("overrides") or {}
    if not isinstance(overrides, dict) or not overrides:
        return _err("overrides must be a non-empty object")
    valid = inventory.names()
    unknown = sorted(t for t in overrides if t not in valid)
    if unknown:
        return _err("unknown tokens", unknown=unknown)
    try:
        theme_file.write_text(_render_css(name, overrides))
    except OSError as e:
        return _err(f"write failed: {e}")
    return json.dumps({
        "ok": True,
        "path": str(theme_file),
        "tokens_written": len(overrides),
    })


def apply_theme(args, **kwargs):
    name, frontend, _theme_file, err = _resolve_named_theme(args, require_exists=True)
    if err:
        return err
    style = _style_css(frontend)
    text = style.read_text()
    block = f"{_SENTINEL_BEGIN}\n@import './themes/{name}.css';\n{_SENTINEL_END}"
    pattern = re.compile(
        re.escape(_SENTINEL_BEGIN) + r".*?" + re.escape(_SENTINEL_END), re.DOTALL,
    )
    if pattern.search(text):
        new_text = pattern.sub(block, text)
    elif _DESIGN_SYSTEM_IMPORT in text:
        new_text = text.replace(
            _DESIGN_SYSTEM_IMPORT, _DESIGN_SYSTEM_IMPORT + "\n" + block, 1,
        )
    else:
        new_text = block + "\n" + text
    if new_text != text:
        try:
            style.write_text(new_text)
        except OSError as e:
            return _err(f"write failed: {e}")
    return json.dumps({"ok": True, "active_theme": name, "style_css": str(style)})


# --- ComfyUI image generation --------------------------------------------

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


_QUALITY_PREFIX = "masterpiece, best quality, score_7, safe, anime, "
_DEFAULT_NEGATIVE = (
    "worst quality, low quality, score_1, score_2, score_3, "
    "blurry, jpeg artifacts, sepia"
)

# Prompt-format Anima/Qwen workflow (subgraph flattened).
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


def _comfy_post(path, body, timeout=30):
    req = urllib.request.Request(
        _comfy_url() + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _comfy_get_bytes(path, timeout=30):
    with urllib.request.urlopen(_comfy_url() + path, timeout=timeout) as r:
        return r.read()


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
        submission = _comfy_post(
            "/prompt",
            {"prompt": workflow, "client_id": "hermes-comfyui-theme-maker"},
        )
    except (urllib.error.URLError, OSError) as e:
        return _err(f"ComfyUI not reachable at {_comfy_url()}: {e}")

    if submission.get("node_errors"):
        return _err("ComfyUI rejected the workflow", node_errors=submission["node_errors"])
    prompt_id = submission.get("prompt_id")
    if not prompt_id:
        return _err("ComfyUI did not return a prompt_id", raw=submission)

    deadline = started + _COMFY_TIMEOUT
    image_ref = None
    while time.time() < deadline:
        try:
            history = json.loads(_comfy_get_bytes(f"/history/{prompt_id}"))
        except (urllib.error.URLError, OSError) as e:
            return _err(f"history poll failed: {e}")
        record = history.get(prompt_id)
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
        data = _comfy_get_bytes(f"/view?{qs}")
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


# --- palette extraction ---------------------------------------------------

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


def render_theme_swatch(args, **kwargs):
    name, _frontend, theme_file, err = _resolve_named_theme(args, require_exists=True)
    if err:
        return err
    matches, groups, err = _load_theme_groups(theme_file)
    if err:
        return err

    lines = ["", f"  \033[1m{name}\033[0m", f"  {len(matches)} overrides", ""]
    for category in _CATEGORY_ORDER:
        if category not in groups:
            continue
        lines.append(f"  \033[1m{category}\033[0m")
        for token, hex_val in sorted(groups[category]):
            lines.append(f"  {_ansi_swatch(hex_val)}  {hex_val}  {token}")
        lines.append("")

    return json.dumps({
        "ok": True,
        "name": name,
        "tokens_in_theme": len(matches),
        "swatch": "\n".join(lines),
    })


_IMAGE_BG = "#0e0e10"
_IMAGE_FG = "#f0eee6"
_IMAGE_MUTED = "#8a8a92"
_IMAGE_SIZE = 1080
_IMAGE_MARGIN = 60


def render_theme_image(args, **kwargs):
    name, _frontend, theme_file, err = _resolve_named_theme(args, require_exists=True)
    if err:
        return err
    matches, groups, err = _load_theme_groups(theme_file)
    if err:
        return err

    try:
        import drawbot_skia.drawbot as db
    except ImportError:
        return _missing_dep_error("drawbot-skia")

    raw_output = ((args or {}).get("output_path") or "").strip()
    if raw_output:
        out_path = Path(raw_output).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        out_path = _cache_dir() / f"{name}.png"

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

    def draw_swatch(x, y_top, w, h, hex_val, label_token):
        fill_hex(hex_val)
        rect_top(x, y_top, w, h)
        text_color = "#0a0a0a" if _hex_luminance(hex_val) > 0.55 else "#f5f5f5"
        fill_hex(text_color)
        text_top(hex_val, x + 14, y_top + 30, "Helvetica-Bold", 20)
        text_top(label_token, x + 14, y_top + 52, "Helvetica", 14)

    def draw_section(title, swatches, y_top, cols=4, swatch_h=78, gutter=14):
        fill_hex(_IMAGE_FG)
        text_top(title, _IMAGE_MARGIN, y_top + 18, "Helvetica-Bold", 20)
        y_grid = y_top + 36
        inner = _IMAGE_SIZE - _IMAGE_MARGIN * 2
        swatch_w = (inner - gutter * (cols - 1)) // cols
        for i, (token, hex_val) in enumerate(swatches):
            col = i % cols
            row = i // cols
            sx = _IMAGE_MARGIN + col * (swatch_w + gutter)
            sy = y_grid + row * (swatch_h + gutter)
            draw_swatch(sx, sy, swatch_w, swatch_h, hex_val, token)
        rows = (len(swatches) + cols - 1) // cols
        return y_grid + rows * (swatch_h + gutter) + 18

    db.newDrawing()
    db.size(_IMAGE_SIZE, _IMAGE_SIZE)
    fill_hex(_IMAGE_BG)
    db.rect(0, 0, _IMAGE_SIZE, _IMAGE_SIZE)

    fill_hex(_IMAGE_FG)
    text_top(name, _IMAGE_MARGIN, 90, "Helvetica-Bold", 56)
    fill_hex(_IMAGE_MUTED)
    text_top(
        f"{len(matches)} token overrides · hermes-comfyui-theme-maker",
        _IMAGE_MARGIN, 125, "Helvetica", 18,
    )

    y = 160
    if "Charcoal (dark neutrals)" in groups:
        ramp = sorted(groups["Charcoal (dark neutrals)"])
        stripe_w = (_IMAGE_SIZE - _IMAGE_MARGIN * 2) // len(ramp)
        for i, (_token, hex_val) in enumerate(ramp):
            fill_hex(hex_val)
            rect_top(_IMAGE_MARGIN + i * stripe_w, y, stripe_w, 50)
        y += 80

    for category in _CATEGORY_ORDER:
        if category in groups:
            y = draw_section(category, sorted(groups[category]), y)

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
        "name": name,
        "path": str(out_path),
        "size": f"{_IMAGE_SIZE}x{_IMAGE_SIZE}",
        "tokens_in_theme": len(matches),
    })
