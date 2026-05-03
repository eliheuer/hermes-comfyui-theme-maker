"""JSON schemas describing the theme-maker tools to the LLM."""

LIST_TOKENS = {
    "name": "list_comfyui_tokens",
    "description": (
        "Return the canonical list of ComfyUI frontend CSS tokens this skill "
        "can override. Call this once at the start of any theming task to "
        "ground decisions in the actual token surface; do not invent token "
        "names that are not in the response."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "layer": {
                "type": "string",
                "enum": [
                    "all",
                    "palette",
                    "extended_palette",
                    "app_mode",
                    "layout",
                ],
                "description": (
                    "Which token layer to return. 'all' (default) is usually "
                    "the right choice for cohesive theming."
                ),
                "default": "all",
            },
        },
    },
}

WRITE_THEME = {
    "name": "write_comfyui_theme",
    "description": (
        "Write a CSS theme file to the ComfyUI frontend's themes directory. "
        "Pass overrides as a flat token-name to value dict. Token names must "
        "come from list_comfyui_tokens; unknown tokens are rejected. The "
        "leading '--' is omitted from token names."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "Theme slug (lowercase, hyphenated, alphanumeric). "
                    "Used as the .css filename."
                ),
            },
            "overrides": {
                "type": "object",
                "description": (
                    "Token-name to CSS-value pairs (e.g. "
                    '{"color-charcoal-800": "#0a0a14"}). Names omit the '
                    "leading '--'. Values must be concrete (hex, rgb, rgba) "
                    "rather than var() references."
                ),
                "additionalProperties": {"type": "string"},
            },
        },
        "required": ["name", "overrides"],
    },
}

APPLY_THEME = {
    "name": "apply_comfyui_theme",
    "description": (
        "Activate a previously-written theme by injecting an @import into the "
        "frontend's main style.css between sentinel comments. Idempotent: "
        "only one theme is active at a time. If a Vite dev server is running "
        "the change hot-reloads."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "Theme slug previously passed to write_comfyui_theme."
                ),
            },
        },
        "required": ["name"],
    },
}

GENERATE_MOOD_IMAGE = {
    "name": "generate_mood_image",
    "description": (
        "Generate a small reference image via the local ComfyUI Anima/Qwen "
        "text-to-image stack. Use this when designing a theme to anchor the "
        "palette in real generated pixels rather than guessing colors from a "
        "description. Returns a path to the generated PNG. Falls back "
        "gracefully if ComfyUI is unreachable; in that case the caller "
        "should skip to text-only theme generation."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": (
                    "Anime-styled positive prompt for the Anima model. The "
                    "stack is anime / non-photorealistic; describe the mood "
                    "and atmosphere directly. Example: 'a campfire in autumn "
                    "forest at dusk, glowing embers, warm orange light, "
                    "fallen leaves'. Quality boilerplate ('masterpiece, best "
                    "quality, ...') is added automatically."
                ),
            },
            "size": {
                "type": "integer",
                "description": (
                    "Square image size in pixels. Default 768; smaller is "
                    "faster, larger is more detail. Capped at 1024."
                ),
                "default": 768,
            },
            "seed": {
                "type": "integer",
                "description": (
                    "Generation seed. Omit for random. Pass a fixed seed to "
                    "reproduce a specific image across runs."
                ),
            },
        },
        "required": ["prompt"],
    },
}

EXTRACT_PALETTE_FROM_IMAGE = {
    "name": "extract_palette_from_image",
    "description": (
        "Extract the N most dominant colors from an image via median-cut "
        "quantization. Use after generate_mood_image to convert the visual "
        "into concrete palette anchors that can be mapped onto ComfyUI's "
        "token ramps (dark anchors -> charcoal-*, warm anchors -> coral-* "
        "or gold-*, etc.). Returns a list of {hex, percent} sorted by "
        "pixel count descending."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Absolute path to a PNG/JPG/WEBP image, or '~/...' "
                    "shorthand. Typically the path returned by "
                    "generate_mood_image."
                ),
            },
            "n_colors": {
                "type": "integer",
                "description": (
                    "Number of dominant colors to return. Default 8. "
                    "More than ~12 starts producing near-duplicates."
                ),
                "default": 8,
            },
        },
        "required": ["path"],
    },
}
