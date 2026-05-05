# ComfyUI Theme Maker

Generate a cohesive ComfyUI theme from a natural-language description.
Output is a **palette JSON** in ComfyUI's canonical schema, registered
via ComfyUI's settings HTTP API so it appears in Settings → Appearance
→ Color Palette and persists across sessions.

The output format matches every community theme repo (shahshrey,
sizzlebop, gmorks, …) and the built-in palettes (Dark, Light, Arc,
Nord, Solarized, Github). Themes are drop-in compatible.

## When to use

User says something like "make ComfyUI dark and synthwave", "theme it
like a 90s terminal", "warm neutrals with a gold accent".

## Tools at a glance

- `list_comfyui_tokens(group?)` — show the schema keys per group.
- `generate_mood_image(prompt, size?, seed?)` — Anima/Qwen reference.
- `extract_palette_from_image(path, n_colors?)` — dominant hex colors.
- `write_comfyui_theme(palette)` — save a palette JSON to cache.
- `apply_comfyui_theme(name)` — register + activate via ComfyUI's
  settings HTTP API. Theme appears in the menu.
- `render_theme_swatch(name)` — ANSI preview in the terminal.
- `render_theme_image(name, output_path?)` — PNG infographic, on
  request only.

ComfyUI must be running locally for `generate_mood_image` and
`apply_comfyui_theme` (default `http://127.0.0.1:8188`).

## Preferred workflow — visual research

1. **`list_comfyui_tokens(group="all")`** to see the full schema.
   Don't invent keys.

2. **Plan a mood prompt** for the diffusion model. Translate the
   user's request into a concrete anime-styled scene; quality
   boilerplate is added automatically.

3. **`generate_mood_image(prompt=…, size=768)`** — typical latency
   10–25 s on M-series.

4. **`extract_palette_from_image(path=…, n_colors=8)`** — returns
   `[{hex, percent}, …]` sorted by pixel count.

5. **Decide light vs dark** from the average lightness of the
   extracted colors. Most "atmosphere" prompts (campfire, deep ocean,
   night city, moss forest) want `light_theme: false`. Sun-bleached,
   pastel, paper-white prompts want `light_theme: true`.

6. **Map extracted colors onto the palette schema** (see *Mapping
   strategy* below). For most themes, populate **comfy_base only**;
   inherit `node_slot` and `litegraph_base` from defaults.

7. **`write_comfyui_theme(palette={…})`** with a fully-shaped
   palette object. Required fields: `id` (slug-cased), `name`,
   `colors: { node_slot: {}, litegraph_base: {}, comfy_base: {…} }`.
   Optional: `light_theme`. Empty groups are valid; the loader
   inherits from defaults.

8. **`apply_comfyui_theme(name=…)`** — registers via ComfyUI's
   `/api/settings/Comfy.CustomColorPalettes` (merge) and sets
   `Comfy.ColorPalette` to the new id. Theme menu picks it up after
   page reload (or immediately on next palette switch).

9. **`render_theme_swatch(name=…)`** — include the returned
   `swatch` string **verbatim** in your reply.

10. **Briefly summarize**: light vs dark, palette source, key colour
    decisions. The user can then iterate.

If the user asks for a **shareable image / social-media version**,
call `render_theme_image(name=…)`. Don't call this in the default
loop.

## Iteration without re-generation

When the user says "warmer", "more contrast", "less saturated", do
**not** call `generate_mood_image` again. Adjust the existing
palette's hex values, re-call `write_comfyui_theme` (overwriting the
same `id`), and `apply_comfyui_theme`.

## Fallback — text-only

If `generate_mood_image` errors, skip steps 3–4 and pick palette
anchors from the description using the heuristics below. Tell the
user visual research was unavailable.

## The palette schema

Three colour groups in `palette.colors`:

| Group | Keys | Role |
|---|---|---|
| `node_slot` | 16 (CLIP, MODEL, IMAGE, …) | Connection-type colours on the canvas. **Usually leave empty** — defaults convey type semantics users know. |
| `litegraph_base` | 25 (NODE_TITLE_COLOR, WIDGET_BGCOLOR, …) | Canvas-internal node rendering. Only override 3-5 for theme cohesion. |
| `comfy_base` | 17 required + 9 optional | UI chrome (panels, menus, inputs, borders). **The main theming surface.** |

Schema reminders:

- All keys are **partial** — every individual key is optional within
  its group. Missing keys inherit from `DEFAULT_DARK_COLOR_PALETTE`
  or `DEFAULT_LIGHT_COLOR_PALETTE`.
- `id` must be slug-cased (lowercase, alphanumeric + hyphens, must
  start with letter or digit).
- `light_theme: true` removes the `.dark-theme` class on
  `document.body` while this palette is active.
- Hex values are 6-digit (`#rrggbb`); 3-digit shortforms are not
  accepted.

## Mapping strategy — extracted colours to palette keys

Sort the extracted colors from `extract_palette_from_image` by
perceived lightness (eyeball — darker hex first). Then assign:

### `comfy_base` (always populate)

For a **dark theme**:

| Key | Take from |
|---|---|
| `bg-color` | Darkest extracted color (or near-darkest) |
| `comfy-menu-bg` | Slightly darker than bg-color (drop ~5-10% lightness) |
| `comfy-menu-secondary-bg` | Between bg-color and content-bg |
| `comfy-input-bg` | Even darker than comfy-menu-bg (input wells should sink) |
| `content-bg` | Mid-dark — between bg-color and a lighter chrome surface |
| `content-hover-bg` | One step lighter than content-bg |
| `tr-even-bg-color`, `tr-odd-bg-color` | Two adjacent lightnesses near content-bg |
| `fg-color` | Lightest extracted color (high-contrast text) |
| `content-fg`, `content-hover-fg` | Same as fg-color (or near it) |
| `input-text` | Slightly less bright than fg-color |
| `descrip-text` | Mid-mute — secondary text |
| `drag-text` | Same family as descrip-text |
| `error-text` | Saturated red (often `#ff4444`) — keep close to default unless user wants to retheme errors |
| `border-color` | Mid-tone neutral, theme-tinted |
| `bar-shadow` | Default `rgba(16,16,16,0.5) 0 0 0.5rem` is fine |

For a **light theme**, mirror the lightness ordering: `bg-color` is
the lightest, `fg-color` the darkest.

### `litegraph_base` (override 3-5 for cohesion)

| Key | Take from |
|---|---|
| `NODE_DEFAULT_BGCOLOR` | A theme-tinted variant of `bg-color`, slightly different so nodes stand out from canvas |
| `NODE_TITLE_COLOR` | Match `descrip-text` or one notch brighter |
| `WIDGET_BGCOLOR` | Same as `comfy-input-bg` for visual unity |
| `LINK_COLOR` | A muted accent — desaturate one of your extracted accents |
| `CLEAR_BACKGROUND_COLOR` | Match `bg-color` so empty canvas matches chrome |

Skip `BACKGROUND_IMAGE` (base64 PNG, leave default) and
`NODE_DEFAULT_SHAPE` (enum, leave default).

### `node_slot` (usually skip)

These colours encode connection-type semantics (CLIP=yellow,
MODEL=purple, LATENT=pink, IMAGE=blue, etc.). Users learn them.
**Leave empty** unless the user explicitly says to retheme connection
colours.

## Design heuristics

- **Contrast first.** Body-text ratio against `bg-color` should
  exceed 7:1.
- **Monotonic neutrals.** The bg surfaces (`bg-color`, `comfy-menu-bg`,
  `comfy-input-bg`, `content-bg`) should step in lightness — no two
  adjacent surfaces at identical brightness.
- **Reserve saturated colors for accents.** Don't make `bg-color`
  vibrant; the canvas is the focus.
- **One identity colour.** Don't introduce two competing
  high-saturation hues.

## Worked example — preferred workflow

**User:** *"make me a campfire theme"*

Plan:
- Mood: warm dark, ember oranges, deep plum-brown neutrals.
- light_theme: false.

Tool calls (abbreviated):

```
list_comfyui_tokens(group="all")
  → schema reference

generate_mood_image(prompt="a quiet campfire in autumn forest at dusk,
                            warm orange glow on burnt logs, soft amber
                            light through leaves, deep ember reds,
                            atmospheric fog")
  → ~/.cache/.../<prompt_id>.png

extract_palette_from_image(path=…, n_colors=8)
  → [{hex:"#181b1e", ...}, {hex:"#bf7c49", ...}, ...]

write_comfyui_theme(palette={
  "id": "campfire-mood",
  "name": "Campfire Mood",
  "light_theme": false,
  "colors": {
    "node_slot": {},
    "litegraph_base": {
      "NODE_DEFAULT_BGCOLOR": "#2b1e16",
      "NODE_TITLE_COLOR": "#bf7c49",
      "WIDGET_BGCOLOR": "#1e1510",
      "LINK_COLOR": "#793d26",
      "CLEAR_BACKGROUND_COLOR": "#15100c"
    },
    "comfy_base": {
      "bg-color": "#15100c",
      "fg-color": "#f5e6d2",
      "comfy-menu-bg": "#0f0a08",
      "comfy-menu-secondary-bg": "#1e1510",
      "comfy-input-bg": "#0a0606",
      "input-text": "#e6cfb6",
      "descrip-text": "#a08070",
      "drag-text": "#c9b8a4",
      "error-text": "#ff5050",
      "border-color": "#3a2820",
      "tr-even-bg-color": "#1e1510",
      "tr-odd-bg-color": "#2b1e16",
      "content-bg": "#2b1e16",
      "content-fg": "#f5e6d2",
      "content-hover-bg": "#3a2820",
      "content-hover-fg": "#f5e6d2",
      "bar-shadow": "rgba(16, 10, 8, 0.5) 0 0 0.5rem"
    }
  }
})

apply_comfyui_theme(name="campfire-mood")

render_theme_swatch(name="campfire-mood")
```

Then summarize:

> Generated a campfire reference (autumn forest, ember light) and
> mapped its palette onto a dark theme. Burnt-wood neutrals from the
> forest tones, ember-amber accents on titles and content surfaces.
> Registered as a custom palette — should appear in Settings →
> Appearance → Color Palette as "Campfire Mood". Reload the page to
> see the menu update. Say "warmer", "more contrast", or "more
> saturation" to iterate.
