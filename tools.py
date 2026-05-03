"""Tool implementations: list, write, apply ComfyUI themes."""

import json
import os
import re
from pathlib import Path

from . import token_inventory as inventory


def _frontend_path() -> Path:
    raw = os.environ.get(
        "HERMES_COMFYUI_FRONTEND_PATH",
        "~/Work/comfy/repos/ComfyUI_frontend",
    )
    return Path(raw).expanduser()


def _themes_dir() -> Path:
    d = _frontend_path() / "src" / "assets" / "css" / "themes"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _style_css() -> Path:
    return _frontend_path() / "src" / "assets" / "css" / "style.css"


_VALID_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_SENTINEL_BEGIN = "/* hermes-comfyui-theme-maker:active */"
_SENTINEL_END = "/* hermes-comfyui-theme-maker:end */"
_DESIGN_SYSTEM_IMPORT = "@import '@comfyorg/design-system/css/style.css';"


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
    if not _VALID_SLUG.match(name):
        return json.dumps({"error": f"invalid theme slug: {name!r}"})
    if not isinstance(overrides, dict) or not overrides:
        return json.dumps({"error": "overrides must be a non-empty object"})

    valid = inventory.names()
    unknown = sorted(t for t in overrides if t not in valid)
    if unknown:
        return json.dumps({"error": "unknown tokens", "unknown": unknown})

    target = _themes_dir() / f"{name}.css"
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
    if not _VALID_SLUG.match(name):
        return json.dumps({"error": f"invalid theme slug: {name!r}"})

    theme_file = _themes_dir() / f"{name}.css"
    if not theme_file.exists():
        return json.dumps({"error": f"theme not found: {theme_file}"})

    style = _style_css()
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
