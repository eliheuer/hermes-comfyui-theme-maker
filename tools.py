"""Tool implementations: list/write/apply themes, generate mood images,
extract dominant palette colors from images.
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


def _resolve_frontend(raw: str) -> tuple[Path | None, str | None]:
    """Resolve a user-supplied frontend path string into a checkout root.

    Returns (path, error_message). On success, error_message is None and
    path is a Path that contains src/assets/css/style.css. On failure,
    path is None and error_message describes what was wrong.
    """
    if not raw:
        return None, "frontend_path is required"
    path = Path(raw).expanduser().resolve()
    if not path.exists():
        return None, f"frontend_path does not exist: {path}"
    style = path / "src" / "assets" / "css" / "style.css"
    if not style.exists():
        return None, (
            f"{path} does not look like a ComfyUI_frontend checkout "
            f"(missing src/assets/css/style.css)"
        )
    return path, None


def _themes_dir(frontend: Path) -> Path:
    d = frontend / "src" / "assets" / "css" / "themes"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _style_css(frontend: Path) -> Path:
    return frontend / "src" / "assets" / "css" / "style.css"


_VALID_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_SENTINEL_BEGIN = "/* hermes-comfyui-theme-maker:active */"
_SENTINEL_END = "/* hermes-comfyui-theme-maker:end */"
_DESIGN_SYSTEM_IMPORT = "@import '@comfyorg/design-system/css/style.css';"
_TOKEN_LINE_RE = re.compile(r"--([a-z][a-z0-9-]*):\s*(#[0-9a-fA-F]{6})")


def list_tokens(args: dict, **kwargs) -> str:
    layer = (args or {}).get("layer", "all")
    if layer == "all":
        rows = inventory.all_tokens()
    else:
        try:
            rows = [
                (n, d, desc, layer) for n, d, desc in inventory.by_layer(layer)
            ]
        except KeyError:
            return json.dumps({"error": f"unknown layer: {layer!r}"})
    payload = [
        {"name": n, "default": d, "description": desc, "layer": lyr}
        for n, d, desc, lyr in rows
    ]
    return json.dumps({"tokens": payload, "count": len(payload)})


def _render_css(name: str, overrides: dict) -> str:
    body = "\n".join(
        f"  --{token}: {value};" for token, value in overrides.items()
    )
    return (
        f"/* hermes-comfyui-theme-maker: {name} */\n"
        ":root {\n"
        f"{body}\n"
        "}\n"
    )


def write_theme(args: dict, **kwargs) -> str:
    args = args or {}
    name = (args.get("name") or "").strip()
    overrides = args.get("overrides") or {}
    raw_path = (args.get("frontend_path") or "").strip()
    if not _VALID_SLUG.match(name):
        return json.dumps({"error": f"invalid theme slug: {name!r}"})
    if not isinstance(overrides, dict) or not overrides:
        return json.dumps({"error": "overrides must be a non-empty object"})

    frontend, err = _resolve_frontend(raw_path)
    if err:
        return json.dumps({"error": err})

    valid = inventory.names()
    unknown = sorted(t for t in overrides if t not in valid)
    if unknown:
        return json.dumps({"error": "unknown tokens", "unknown": unknown})

    target = _themes_dir(frontend) / f"{name}.css"
    css = _render_css(name, overrides)
    try:
        target.write_text(css)
    except OSError as e:
        return json.dumps({"error": f"write failed: {e}"})
    return json.dumps(
        {
            "ok": True,
            "path": str(target),
            "tokens_written": len(overrides),
        }
    )


def apply_theme(args: dict, **kwargs) -> str:
    args = args or {}
    name = (args.get("name") or "").strip()
    raw_path = (args.get("frontend_path") or "").strip()
    if not _VALID_SLUG.match(name):
        return json.dumps({"error": f"invalid theme slug: {name!r}"})

    frontend, err = _resolve_frontend(raw_path)
    if err:
        return json.dumps({"error": err})

    theme_file = _themes_dir(frontend) / f"{name}.css"
    if not theme_file.exists():
        return json.dumps({"error": f"theme not found: {theme_file}"})

    style = _style_css(frontend)
    if not style.exists():
        return json.dumps({"error": f"style.css missing: {style}"})

    text = style.read_text()
    block = (
        f"{_SENTINEL_BEGIN}\n"
        f"@import './themes/{name}.css';\n"
        f"{_SENTINEL_END}"
    )
    pattern = re.compile(
        re.escape(_SENTINEL_BEGIN) + r".*?" + re.escape(_SENTINEL_END),
        re.DOTALL,
    )
    if pattern.search(text):
        new_text = pattern.sub(block, text)
    elif _DESIGN_SYSTEM_IMPORT in text:
        new_text = text.replace(
            _DESIGN_SYSTEM_IMPORT,
            _DESIGN_SYSTEM_IMPORT + "\n" + block,
            1,
        )
    else:
        new_text = block + "\n" + text

    if new_text != text:
        try:
            style.write_text(new_text)
        except OSError as e:
            return json.dumps({"error": f"write failed: {e}"})
    return json.dumps(
        {
            "ok": True,
            "active_theme": name,
            "style_css": str(style),
        }
    )


# ---------------------------------------------------------------------------
# Layer 2: ComfyUI image generation + palette extraction
# ---------------------------------------------------------------------------

def _comfy_url() -> str:
    return os.environ.get(
        "HERMES_COMFYUI_API_URL", "http://127.0.0.1:8188"
    ).rstrip("/")


def _cache_dir() -> Path:
    raw = os.environ.get(
        "HERMES_COMFYUI_CACHE_DIR",
        "~/.cache/hermes-comfyui-theme-maker",
    )
    d = Path(raw).expanduser()
    d.mkdir(parents=True, exist_ok=True)
    return d


# Quality boilerplate auto-prepended to user prompts. Mirrors the saved
# Anima turbo workflow's positive prompt prefix.
_QUALITY_PREFIX = "masterpiece, best quality, score_7, safe, anime, "

# Default negative prompt — matches the saved Anima turbo workflow.
_DEFAULT_NEGATIVE = (
    "worst quality, low quality, score_1, score_2, score_3, "
    "blurry, jpeg artifacts, sepia"
)

# Prompt-format workflow derived from the user's saved
# image_anima_preview--turbo.app.json. Subgraph is flattened. Verified
# end-to-end against ComfyUI v0.19.3 on 2026-05-03.
_ANIMA_WORKFLOW: dict = {
    "1": {
        "class_type": "UNETLoader",
        "inputs": {
            "unet_name": "anima-preview.safetensors",
            "weight_dtype": "default",
        },
    },
    "2": {
        "class_type": "CLIPLoader",
        "inputs": {
            "clip_name": "qwen_3_06b_base.safetensors",
            "type": "stable_diffusion",
            "device": "default",
        },
    },
    "3": {
        "class_type": "VAELoader",
        "inputs": {"vae_name": "qwen_image_vae.safetensors"},
    },
    "4": {
        "class_type": "LoraLoader",
        "inputs": {
            "model": ["1", 0],
            "clip": ["2", 0],
            "lora_name": "anima-turbo-lora-v0.1.safetensors",
            "strength_model": 0.9,
            "strength_clip": 0.9,
        },
    },
    "5": {
        "class_type": "CLIPTextEncode",
        "inputs": {"clip": ["4", 1], "text": ""},
    },
    "6": {
        "class_type": "CLIPTextEncode",
        "inputs": {"clip": ["4", 1], "text": _DEFAULT_NEGATIVE},
    },
    "7": {
        "class_type": "EmptyLatentImage",
        "inputs": {"width": 768, "height": 768, "batch_size": 1},
    },
    "8": {
        "class_type": "KSampler",
        "inputs": {
            "model": ["4", 0],
            "positive": ["5", 0],
            "negative": ["6", 0],
            "latent_image": ["7", 0],
            "seed": 0,
            "steps": 8,
            "cfg": 1.0,
            "sampler_name": "er_sde",
            "scheduler": "simple",
            "denoise": 1.0,
        },
    },
    "9": {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["8", 0], "vae": ["3", 0]},
    },
    "10": {
        "class_type": "SaveImage",
        "inputs": {"images": ["9", 0], "filename_prefix": "hermes-mood"},
    },
}

_COMFY_TIMEOUT = 90  # seconds end-to-end (submit + poll + fetch)
_MAX_SIZE = 1024
_MIN_SIZE = 256


def _build_workflow(prompt: str, size: int, seed: int) -> dict:
    wf = copy.deepcopy(_ANIMA_WORKFLOW)
    wf["5"]["inputs"]["text"] = _QUALITY_PREFIX + prompt
    wf["7"]["inputs"]["width"] = size
    wf["7"]["inputs"]["height"] = size
    wf["8"]["inputs"]["seed"] = seed
    return wf


def _comfy_post(path: str, body: dict, timeout: int = 30) -> dict:
    req = urllib.request.Request(
        _comfy_url() + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _comfy_get_bytes(path: str, timeout: int = 30) -> bytes:
    with urllib.request.urlopen(_comfy_url() + path, timeout=timeout) as r:
        return r.read()


def _comfy_get_json(path: str, timeout: int = 30) -> dict:
    return json.loads(_comfy_get_bytes(path, timeout))


def generate_mood_image(args: dict, **kwargs) -> str:
    args = args or {}
    prompt = (args.get("prompt") or "").strip()
    if not prompt:
        return json.dumps({"error": "prompt is required"})
    size = int(args.get("size") or 768)
    if not (_MIN_SIZE <= size <= _MAX_SIZE):
        return json.dumps(
            {"error": f"size must be between {_MIN_SIZE} and {_MAX_SIZE}"}
        )
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
        return json.dumps(
            {"error": f"ComfyUI not reachable at {_comfy_url()}: {e}"}
        )

    if submission.get("node_errors"):
        return json.dumps(
            {
                "error": "ComfyUI rejected the workflow",
                "node_errors": submission["node_errors"],
            }
        )
    prompt_id = submission.get("prompt_id")
    if not prompt_id:
        return json.dumps(
            {"error": "ComfyUI did not return a prompt_id", "raw": submission}
        )

    deadline = started + _COMFY_TIMEOUT
    image_ref = None
    while time.time() < deadline:
        try:
            history = _comfy_get_json(f"/history/{prompt_id}")
        except (urllib.error.URLError, OSError) as e:
            return json.dumps({"error": f"history poll failed: {e}"})
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
        return json.dumps(
            {"error": f"timeout after {_COMFY_TIMEOUT}s with no output image"}
        )

    qs = urllib.parse.urlencode(
        {
            "filename": image_ref["filename"],
            "type": image_ref.get("type", "output"),
            "subfolder": image_ref.get("subfolder", ""),
        }
    )
    try:
        data = _comfy_get_bytes(f"/view?{qs}")
    except (urllib.error.URLError, OSError) as e:
        return json.dumps({"error": f"failed to fetch image: {e}"})

    out = _cache_dir() / f"{prompt_id}.png"
    try:
        out.write_bytes(data)
    except OSError as e:
        return json.dumps({"error": f"failed to cache image: {e}"})

    return json.dumps(
        {
            "ok": True,
            "path": str(out),
            "prompt_id": prompt_id,
            "seed": seed,
            "size": size,
            "elapsed_seconds": round(time.time() - started, 2),
        }
    )


def _categorize_token(token: str) -> str:
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


def _ansi_swatch(hex_value: str, width: int = 4) -> str:
    """Return an ANSI 24-bit colored block of the given width (in cells)."""
    r = int(hex_value[1:3], 16)
    g = int(hex_value[3:5], 16)
    b = int(hex_value[5:7], 16)
    return f"\033[48;2;{r};{g};{b}m{' ' * width}\033[0m"


def render_theme_swatch(args: dict, **kwargs) -> str:
    args = args or {}
    name = (args.get("name") or "").strip()
    raw_path = (args.get("frontend_path") or "").strip()
    if not _VALID_SLUG.match(name):
        return json.dumps({"error": f"invalid theme slug: {name!r}"})

    frontend, err = _resolve_frontend(raw_path)
    if err:
        return json.dumps({"error": err})

    theme_file = _themes_dir(frontend) / f"{name}.css"
    if not theme_file.exists():
        return json.dumps({"error": f"theme not found: {theme_file}"})

    text = theme_file.read_text()
    matches = _TOKEN_LINE_RE.findall(text)
    if not matches:
        return json.dumps(
            {"error": f"no token overrides found in {theme_file}"}
        )

    groups: dict = {}
    for token, hex_val in matches:
        groups.setdefault(_categorize_token(token), []).append(
            (token, hex_val.lower())
        )

    lines = ["", f"  \033[1m{name}\033[0m", f"  {len(matches)} overrides", ""]
    for category in _CATEGORY_ORDER:
        if category not in groups:
            continue
        lines.append(f"  \033[1m{category}\033[0m")
        for token, hex_val in sorted(groups[category]):
            lines.append(
                f"  {_ansi_swatch(hex_val)}  {hex_val}  {token}"
            )
        lines.append("")

    return json.dumps(
        {
            "ok": True,
            "name": name,
            "tokens_in_theme": len(matches),
            "swatch": "\n".join(lines),
        }
    )


_IMAGE_BG = "#0e0e10"
_IMAGE_FG = "#f0eee6"
_IMAGE_MUTED = "#8a8a92"
_IMAGE_SIZE = 1080
_IMAGE_MARGIN = 60


def _hex_rgb01(hex_value: str) -> tuple:
    return (
        int(hex_value[1:3], 16) / 255.0,
        int(hex_value[3:5], 16) / 255.0,
        int(hex_value[5:7], 16) / 255.0,
    )


def _hex_luminance(hex_value: str) -> float:
    r, g, b = _hex_rgb01(hex_value)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def render_theme_image(args: dict, **kwargs) -> str:
    args = args or {}
    name = (args.get("name") or "").strip()
    raw_path = (args.get("frontend_path") or "").strip()
    raw_output = (args.get("output_path") or "").strip()
    if not _VALID_SLUG.match(name):
        return json.dumps({"error": f"invalid theme slug: {name!r}"})

    frontend, err = _resolve_frontend(raw_path)
    if err:
        return json.dumps({"error": err})

    theme_file = _themes_dir(frontend) / f"{name}.css"
    if not theme_file.exists():
        return json.dumps({"error": f"theme not found: {theme_file}"})

    matches = _TOKEN_LINE_RE.findall(theme_file.read_text())
    if not matches:
        return json.dumps({"error": f"no token overrides found in {theme_file}"})

    try:
        import drawbot_skia.drawbot as db
    except ImportError:
        return json.dumps(
            {
                "error": (
                    "drawbot-skia is not installed in hermes-agent's venv. "
                    "From a shell, run:\n"
                    "  ~/.hermes/hermes-agent/venv/bin/pip install "
                    "-r requirements.txt\n"
                    "(Use the full path — running plain `pip install` will "
                    "install into the wrong Python.)"
                )
            }
        )

    if raw_output:
        out_path = Path(raw_output).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        out_path = _cache_dir() / f"{name}.png"

    groups: dict = {}
    for token, hex_val in matches:
        groups.setdefault(_categorize_token(token), []).append(
            (token, hex_val.lower())
        )

    def yflip(y_top: float) -> float:
        return _IMAGE_SIZE - y_top

    def fill_hex(hex_value: str) -> None:
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
        fill_hex(text_color)
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
        _IMAGE_MARGIN,
        125,
        "Helvetica",
        18,
    )

    y = 160
    if "Charcoal (dark neutrals)" in groups:
        ramp = sorted(groups["Charcoal (dark neutrals)"])
        stripe_w = (_IMAGE_SIZE - _IMAGE_MARGIN * 2) // len(ramp)
        for i, (_token, hex_val) in enumerate(ramp):
            fill_hex(hex_val)
            rect_top(_IMAGE_MARGIN + i * stripe_w, y, stripe_w, 50)
        y += 50 + 30

    for category in _CATEGORY_ORDER:
        if category in groups:
            y = draw_section(category, sorted(groups[category]), y)

    fill_hex(_IMAGE_MUTED)
    text_top(
        "github.com/eliheuer/hermes-comfyui-theme-maker · GPL-3.0",
        _IMAGE_MARGIN,
        _IMAGE_SIZE - 36,
        "Helvetica",
        14,
    )

    try:
        db.saveImage(str(out_path))
    finally:
        db.endDrawing()

    return json.dumps(
        {
            "ok": True,
            "name": name,
            "path": str(out_path),
            "size": f"{_IMAGE_SIZE}x{_IMAGE_SIZE}",
            "tokens_in_theme": len(matches),
        }
    )


def extract_palette_from_image(args: dict, **kwargs) -> str:
    args = args or {}
    raw_path = args.get("path") or ""
    n_colors = int(args.get("n_colors") or 8)
    if not raw_path:
        return json.dumps({"error": "path is required"})
    if not (1 <= n_colors <= 32):
        return json.dumps({"error": "n_colors must be 1-32"})

    try:
        from PIL import Image
    except ImportError:
        return json.dumps(
            {
                "error": (
                    "Pillow is not installed in hermes-agent's venv. "
                    "From a shell, run:\n"
                    "  ~/.hermes/hermes-agent/venv/bin/pip install "
                    "-r requirements.txt\n"
                    "(Use the full path — running plain `pip install` will "
                    "install into the wrong Python.)"
                )
            }
        )

    path = Path(raw_path).expanduser()
    if not path.exists():
        return json.dumps({"error": f"image not found: {path}"})

    try:
        img = Image.open(path).convert("RGB")
    except Exception as e:
        return json.dumps({"error": f"could not open image: {e}"})

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
    colors = [
        {"hex": h, "percent": round(100 * c / total, 1)} for c, h in rows
    ]
    return json.dumps({"ok": True, "colors": colors, "source": str(path)})
