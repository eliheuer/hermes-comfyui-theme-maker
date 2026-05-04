"""Canonical inventory of ComfyUI_frontend CSS tokens the theme maker overrides.

Sourced from:
  packages/design-system/src/css/_palette.css       (palette layer)
  packages/design-system/src/css/style.css          (extended palette + layout)
  src/assets/css/style.css                          (app-mode layer, PR #11317)
"""

# Layer 1: foundational palette ramps from _palette.css.
PALETTE = [
    ("color-charcoal-100", "#55565e", "lightest charcoal"),
    ("color-charcoal-200", "#494a50", ""),
    ("color-charcoal-300", "#3c3d42", ""),
    ("color-charcoal-400", "#313235", ""),
    ("color-charcoal-500", "#2d2e32", ""),
    ("color-charcoal-600", "#262729", "primary node surface (dark)"),
    ("color-charcoal-700", "#202121", "tooltip / accent-primary (light)"),
    ("color-charcoal-800", "#171718", "primary background (dark)"),
    ("color-neutral-550", "#636363", ""),
    ("color-ash-300", "#bbbbbb", ""),
    ("color-ash-500", "#828282", "secondary text"),
    ("color-ash-800", "#444444", ""),
    ("color-smoke-100", "#f3f3f3", ""),
    ("color-smoke-200", "#e9e9e9", "button hover surface (light)"),
    ("color-smoke-300", "#e1e1e1", ""),
    ("color-smoke-400", "#d9d9d9", "button active surface (light)"),
    ("color-smoke-500", "#c5c5c5", ""),
    ("color-smoke-600", "#b4b4b4", ""),
    ("color-smoke-700", "#a0a0a0", ""),
    ("color-smoke-800", "#8a8a8a", ""),
    ("color-white", "#ffffff", "base background (light)"),
    ("color-black", "#000000", ""),
    ("color-electric-400", "#f0ff41", "brand yellow"),
    ("color-sapphire-700", "#172dd7", "brand blue"),
]

# Layer 2: extended palette declared in design-system style.css @theme block.
EXTENDED_PALETTE = [
    ("color-ivory-100", "#fdfbfa", ""),
    ("color-ivory-200", "#faf9f5", ""),
    ("color-ivory-300", "#f0eee6", ""),
    ("color-sand-100", "#e1ded5", ""),
    ("color-sand-200", "#fff7d5", ""),
    ("color-sand-300", "#888682", ""),
    ("color-sand-400", "#eed7ac", ""),
    ("color-slate-100", "#9c9eab", ""),
    ("color-slate-200", "#9fa2bd", ""),
    ("color-slate-300", "#5b5e7d", ""),
    ("color-azure-300", "#78bae9", ""),
    ("color-azure-400", "#31b9f4", "primary background (light)"),
    ("color-azure-600", "#0b8ce9", "primary background (dark)"),
    ("color-cobalt-800", "#185a8b", "primary hover (light)"),
    ("color-jade-400", "#47e469", ""),
    ("color-jade-600", "#00cd72", "success background"),
    ("color-graphite-400", "#9c9eab", ""),
    ("color-gold-400", "#fcbf64", "warning background (light)"),
    ("color-gold-500", "#fdab34", "warning hover"),
    ("color-gold-600", "#fd9903", "warning background (dark)"),
    ("color-coral-500", "#f75951", "destructive background (light)"),
    ("color-coral-600", "#e04e48", "destructive hover"),
    ("color-coral-700", "#b33a3a", "destructive background (dark)"),
    ("color-magenta-300", "#ceaac9", ""),
    ("color-magenta-700", "#6a246a", "bypass color"),
    ("color-ocean-300", "#badde8", "builder mode background (light)"),
    ("color-ocean-600", "#2f687a", "builder mode button background"),
    ("color-ocean-900", "#253236", "builder mode background (dark)"),
    ("color-danger-100", "#c02323", ""),
    ("color-danger-200", "#d62952", ""),
    ("color-bypass", "#6a246a", ""),
    ("color-error", "#962a2a", "error stroke / text"),
]

# Layer 3: app-mode tokens added by PR #11317 (app-mode-semi-customizable-layout).
# Hard-coded hex in src/assets/css/style.css :root, pending theme-system redesign.
APP_MODE = [
    ("app-mode-go-bg", "#279252", "Run button background"),
    ("app-mode-go-bg-hover", "#35a361", "Run button hover"),
    ("app-mode-go-border", "#2c7c49", "Run button border"),
    ("app-mode-stop-bg", "#ef4444", "Stop button background"),
    ("app-mode-stop-bg-hover", "#f87171", "Stop button hover"),
    ("app-mode-stop-border", "#b91c1c", "Stop button border"),
]

# Layer 4: layout color tokens in design-system style.css @theme block.
# These reference primevue --p-* tokens; usually safe at default.
LAYOUT = [
    ("color-layout-canvas", "var(--p-content-background)", "App-mode workspace background"),
    ("color-layout-cell", "var(--p-surface-800)", "Floating panel surface"),
    ("color-layout-cell-hover", "var(--p-surface-700)", "Cell hover"),
    ("color-layout-text", "var(--p-text-color)", "Primary text in app mode"),
    ("color-layout-mute", "var(--p-text-muted-color)", "Muted text in app mode"),
]


_LAYERS = {
    "palette": PALETTE,
    "extended_palette": EXTENDED_PALETTE,
    "app_mode": APP_MODE,
    "layout": LAYOUT,
}


def all_tokens():
    out = []
    for layer_name, rows in _LAYERS.items():
        for name, default, desc in rows:
            out.append((name, default, desc, layer_name))
    return out


def by_layer(layer: str):
    return list(_LAYERS[layer])


def names():
    return {name for name, _, _, _ in all_tokens()}
