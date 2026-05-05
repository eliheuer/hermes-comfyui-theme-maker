"""JSON schemas describing the theme-maker tools to the LLM."""

LIST_COMFYUI_TOKENS = {
    "name": "list_comfyui_tokens",
    "description": (
        "Return the canonical ComfyUI palette schema keys, grouped by "
        "(node_slot, litegraph_base, comfy_base). Call this once at the "
        "start of any theming task to see what keys you can populate. "
        "The schema mirrors the official ComfyUI_frontend Zod schema "
        "(src/schemas/colorPaletteSchema.ts); generated themes are "
        "drop-in compatible with community palettes and the built-in "
        "theme menu."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "group": {
                "type": "string",
                "enum": ["all", "node_slot", "litegraph_base", "comfy_base"],
                "default": "all",
                "description": (
                    "Which group's keys to return. 'all' returns the "
                    "full schema reference."
                ),
            },
        },
    },
}

WRITE_COMFYUI_THEME = {
    "name": "write_comfyui_theme",
    "description": (
        "Save a palette JSON to the local cache. The palette must match "
        "the canonical ComfyUI schema: { id, name, light_theme?, "
        "colors: { node_slot: {...}, litegraph_base: {...}, comfy_base: "
        "{...} } }. Each colors group is a partial dict — only include "
        "keys you want to override; missing keys inherit from the "
        "matching default palette (DEFAULT_DARK or DEFAULT_LIGHT). "
        "Most generated themes only override comfy_base + a handful of "
        "litegraph_base keys; node_slot is usually left empty so "
        "connection-type colors stay recognizable. Call "
        "list_comfyui_tokens first to see valid keys per group."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "palette": {
                "type": "object",
                "description": (
                    "The full palette object. Required fields: id "
                    "(slug-cased string, alphanumeric + hyphens), name "
                    "(human-readable), colors (object with node_slot, "
                    "litegraph_base, comfy_base sub-objects, each "
                    "containing only the keys you wish to override). "
                    "Optional: light_theme (boolean — set true to "
                    "remove .dark-theme class while this palette is "
                    "active)."
                ),
                "required": ["id", "name", "colors"],
            },
        },
        "required": ["palette"],
    },
}

APPLY_COMFYUI_THEME = {
    "name": "apply_comfyui_theme",
    "description": (
        "Register a previously-written theme as a ComfyUI custom "
        "palette and set it as active, via ComfyUI's settings HTTP "
        "API. The theme appears in Settings → Appearance → Color "
        "Palette and applies on the next page load. Idempotent. "
        "Requires ComfyUI running locally (default 127.0.0.1:8188; "
        "override with HERMES_COMFYUI_API_URL env var)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "Theme id previously passed to write_comfyui_theme."
                ),
            },
        },
        "required": ["name"],
    },
}

GENERATE_MOOD_IMAGE = {
    "name": "generate_mood_image",
    "description": (
        "Generate a small reference image via the local ComfyUI "
        "Anima/Qwen text-to-image stack. Use to anchor palette "
        "decisions in real generated pixels. Returns the cached PNG "
        "path."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": (
                    "Anime-styled positive prompt. Quality boilerplate "
                    "is added automatically — describe mood + colour "
                    "directly."
                ),
            },
            "size": {
                "type": "integer",
                "default": 768,
                "description": "Square pixel size, 256-1024.",
            },
            "seed": {
                "type": "integer",
                "description": "Optional fixed seed; random if omitted.",
            },
        },
        "required": ["prompt"],
    },
}

EXTRACT_PALETTE_FROM_IMAGE = {
    "name": "extract_palette_from_image",
    "description": (
        "Extract the N most dominant colors from an image via "
        "median-cut quantization. Use after generate_mood_image to "
        "convert pixels into hex anchors. Returns "
        "[{hex, percent}, ...] sorted by pixel count descending."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "n_colors": {"type": "integer", "default": 8},
        },
        "required": ["path"],
    },
}

RENDER_THEME_SWATCH = {
    "name": "render_theme_swatch",
    "description": (
        "Render a previously-written theme as ANSI-colored swatches "
        "for terminal display, grouped by schema group. Include the "
        "returned 'swatch' string verbatim in your reply so the "
        "user sees the colors in their terminal."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
        },
        "required": ["name"],
    },
}

RENDER_THEME_IMAGE = {
    "name": "render_theme_image",
    "description": (
        "Render a 1080×1080 PNG infographic of a theme. Call only on "
        "explicit user request (e.g. 'make a shareable image' or "
        "'social-media version'). Returns the saved file path."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "output_path": {
                "type": "string",
                "description": (
                    "Optional. Default: "
                    "~/.cache/hermes-comfyui-theme-maker/<name>.png"
                ),
            },
        },
        "required": ["name"],
    },
}
