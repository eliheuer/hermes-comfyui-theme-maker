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
