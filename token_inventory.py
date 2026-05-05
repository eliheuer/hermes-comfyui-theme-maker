"""Canonical ComfyUI palette schema reference.

Mirrors the Zod schema at src/schemas/colorPaletteSchema.ts in
ComfyUI_frontend. Three groups:

- node_slot   (16 keys, all required) — colors for canvas connection
              types (CLIP, MODEL, IMAGE, ...). Semantically meaningful;
              users read connection type at a glance from color.
- litegraph_base (25 keys, all required in the schema but our generator
              treats most as optional) — canvas-internal node rendering
              (titles, widgets, links, slots).
- comfy_base  (18 required + 9 optional) — UI chrome around the canvas
              (panels, menus, inputs, borders, table rows).

A palette JSON looks like:

    {
      "id": "campfire-mood",
      "name": "Campfire Mood",
      "light_theme": false,
      "colors": {
        "node_slot": { ... },
        "litegraph_base": { ... },
        "comfy_base": { ... }
      }
    }

Each group's individual keys are optional in `partialColorsSchema` —
the loader merges with DEFAULT_DARK_COLOR_PALETTE or
DEFAULT_LIGHT_COLOR_PALETTE to fill missing keys. Our generator
typically only overrides comfy_base + a few litegraph_base keys; node
slots stay at defaults so the CLIP/MODEL/etc. colors remain
recognizable.
"""

# 16 connection-type colors. Defaults convey type semantics — users
# learn that CLIP is yellow, MODEL is purple, etc. — so most generated
# themes leave node_slot empty and inherit defaults.
NODE_SLOT_KEYS = [
    "CLIP", "CLIP_VISION", "CLIP_VISION_OUTPUT",
    "CONDITIONING", "CONTROL_NET",
    "IMAGE", "LATENT", "MASK", "MODEL", "STYLE_MODEL", "VAE",
    "NOISE", "GUIDER", "SAMPLER", "SIGMAS", "TAESD",
]

# 25 canvas-rendering keys. Set as JS properties on app.canvas plus
# some CSS variables for the Vue node renderer. NODE_DEFAULT_SHAPE is
# an enum (BOX_SHAPE / ROUND_SHAPE / CARD_SHAPE), BACKGROUND_IMAGE is
# a base64 PNG (the canvas grid) — both stored in this group but not
# colors. Generators typically override only NODE_DEFAULT_BGCOLOR,
# NODE_TITLE_COLOR, WIDGET_BGCOLOR, LINK_COLOR, and CLEAR_BACKGROUND_COLOR.
LITEGRAPH_BASE_KEYS = [
    "BACKGROUND_IMAGE",
    "CLEAR_BACKGROUND_COLOR",
    "NODE_TITLE_COLOR",
    "NODE_SELECTED_TITLE_COLOR",
    "NODE_TEXT_COLOR",
    "NODE_TEXT_HIGHLIGHT_COLOR",
    "NODE_DEFAULT_COLOR",
    "NODE_DEFAULT_BGCOLOR",
    "NODE_DEFAULT_BOXCOLOR",
    "NODE_DEFAULT_SHAPE",
    "NODE_BOX_OUTLINE_COLOR",
    "NODE_BYPASS_BGCOLOR",
    "NODE_ERROR_COLOUR",
    "DEFAULT_SHADOW_COLOR",
    "WIDGET_BGCOLOR",
    "WIDGET_OUTLINE_COLOR",
    "WIDGET_TEXT_COLOR",
    "WIDGET_SECONDARY_TEXT_COLOR",
    "WIDGET_DISABLED_TEXT_COLOR",
    "LINK_COLOR",
    "EVENT_LINK_COLOR",
    "CONNECTING_LINK_COLOR",
    "BADGE_FG_COLOR",
    "BADGE_BG_COLOR",
]

# 18 required UI-chrome keys. Applied as CSS custom properties on
# :root via rootStyle.setProperty('--' + key, value) in
# colorPaletteService.loadComfyColorPalette.
COMFY_BASE_REQUIRED_KEYS = [
    "fg-color",
    "bg-color",
    "comfy-menu-bg",
    "comfy-menu-secondary-bg",
    "comfy-input-bg",
    "input-text",
    "descrip-text",
    "drag-text",
    "error-text",
    "border-color",
    "tr-even-bg-color",
    "tr-odd-bg-color",
    "content-bg",
    "content-fg",
    "content-hover-bg",
    "content-hover-fg",
    "bar-shadow",
]

# 9 optional UI-chrome keys. Loader falls back to var(--palette-${key})
# design-system defaults when a palette omits them.
COMFY_BASE_OPTIONAL_KEYS = [
    "bg-img",
    "contrast-mix-color",
    "interface-stroke",
    "interface-panel-surface",
    "interface-panel-box-shadow",
    "interface-panel-drop-shadow",
    "interface-panel-hover-surface",
    "interface-panel-selected-surface",
    "interface-button-hover-surface",
]

COMFY_BASE_KEYS = COMFY_BASE_REQUIRED_KEYS + COMFY_BASE_OPTIONAL_KEYS


def all_groups():
    return {
        "node_slot": NODE_SLOT_KEYS,
        "litegraph_base": LITEGRAPH_BASE_KEYS,
        "comfy_base": COMFY_BASE_KEYS,
    }


def all_keys():
    return {
        *NODE_SLOT_KEYS,
        *LITEGRAPH_BASE_KEYS,
        *COMFY_BASE_KEYS,
    }


def group_of(key):
    if key in NODE_SLOT_KEYS:
        return "node_slot"
    if key in LITEGRAPH_BASE_KEYS:
        return "litegraph_base"
    if key in COMFY_BASE_KEYS:
        return "comfy_base"
    return None
