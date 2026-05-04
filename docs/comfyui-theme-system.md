# How ComfyUI's theme system actually works

A practical guide to the existing color-palette system in
ComfyUI_frontend, where our generator currently bypasses it, why your
applied theme doesn't show in the theme menu, and concrete PR-able
improvements. Grounded in the current source on branch
`app-mode-semi-customizable-layout` (PR #11317).

## Three CSS layers, only one of which has a registry

ComfyUI_frontend has *three* distinct sources of UI color at runtime.
Only the first is a "theme system" with a UI; the other two are
plain stylesheets the palette system can't see:

1. **Palette layer** — the official theme system. JSON schema, Pinia
   store, settings persistence, settings-menu picker. **6 built-ins
   ship today** (Dark, Light, Arc, Nord, Solarized, Github). Custom
   palettes import into the menu.
2. **Semantic layer** (`packages/design-system/src/css/style.css`) —
   semantic tokens that reference the palette via `var()`. Two
   blocks: `:root` (light) and `.dark-theme` (dark). The palette
   system overrides palette-level vars; semantic vars resolve through
   the cascade automatically.
3. **App-mode layer** (`src/assets/css/style.css`, introduced by PR
   #11317) — local tokens for the new App Mode redesign:
   `--app-mode-go-*`, `--app-mode-stop-*`, `--app-mode-widget-*`.
   **These are not in the palette schema and the palette system
   cannot override them.**

The palette system reaches layers 1 and (transitively) 2. The new
app-mode layer sits outside it. This is the load-bearing gap.

## The palette system in detail

### Data model

A palette is a JSON object with this shape (Zod-validated at
`src/schemas/colorPaletteSchema.ts:99-106`):

```json
{
  "id": "dark",
  "name": "Dark (Default)",
  "light_theme": false,
  "colors": {
    "node_slot":     { "CLIP": "#FFD500", "MODEL": "#B39DDB", ... },
    "litegraph_base":{ "NODE_TITLE_COLOR": "...", "WIDGET_BGCOLOR": "...", ... },
    "comfy_base":    { "fg-color": "...", "bg-color": "...", "comfy-menu-bg": "...", ... }
  }
}
```

Three color groups, each maps to a different rendering surface:

- `node_slot` — colors for connection types on canvas (CLIP, MODEL,
  LATENT, IMAGE, …) — 16 keys.
- `litegraph_base` — canvas-level node rendering (titles, widgets,
  links) — 23 keys, applied as JS properties on `app.canvas` (e.g.
  `app.canvas.node_title_color = …`) plus some CSS variables on
  `document.documentElement`.
- `comfy_base` — outer chrome (UI panels, menus, inputs, borders) —
  ~18 keys, applied as CSS custom properties via
  `rootStyle.setProperty('--' + key, value)`.

### Built-in palettes

`src/constants/coreColorPalettes.ts:1-6` imports JSON files from
`src/assets/palettes/`: `dark.json`, `light.json`, `arc.json`,
`nord.json`, `solarized.json`, `github.json`.

### State and persistence

`src/stores/workspace/colorPaletteStore.ts`:

- `customPalettes` — in-memory ref of user-imported palettes.
- `activePaletteId` — string ref for the currently-applied palette.
- `palettesLookup` — computed merge of `CORE_COLOR_PALETTES +
  customPalettes`.
- `palettes` — computed list, used by the picker UI.

Settings persistence (Pinia → backend, `src/constants/coreSettings.ts`):

- `Comfy.ColorPalette` (line ~950) — active palette id (default
  `'dark'`).
- `Comfy.CustomColorPalettes` (line ~963) — dict of imported custom
  palettes (default `{}`). Both are hidden settings.

### Loader

`src/services/colorPaletteService.ts:249-270` does the actual
"apply" when `activePaletteId` changes:

1. Fetches the palette from `palettesLookup`.
2. Fills missing optional keys from `DEFAULT_DARK_COLOR_PALETTE` /
   `DEFAULT_LIGHT_COLOR_PALETTE`.
3. Calls a chain of sub-loaders that each touch one rendering target:
   - `loadLinkColorPalette` — sets LiteGraph
     `default_connection_color_byType` for the canvas slot dots.
   - `loadLiteGraphColorPalette` — sets canvas object properties
     (`app.canvas.node_title_color = …`, etc.).
   - `loadLitegraphForVueNodes` — injects `--component-node-*` CSS
     variables for the Vue node renderer.
   - `loadLinkColorPaletteForVueNodes` — injects
     `--color-datatype-{type}` CSS variables.
   - `loadComfyColorPalette` — injects `comfy_base` keys as CSS
     variables on `:root` (the line you're most likely to care
     about: `colorPaletteService.ts:209-226`).

### UI: the theme menu

`src/components/sidebar/ComfyMenuButton.vue:182-194` builds the menu
from `colorPaletteStore.palettes`. Each palette gets one menu item;
the active one shows a checkmark. Clicking calls
`colorPaletteService.loadColorPalette(id)` which updates
`activePaletteId`, which a watcher (`GraphCanvas.vue:399-404`)
persists back into `Comfy.ColorPalette` settings.

The picker source of truth is the **store** — not stylesheets, not
files on disk. Anything that wants to be in the picker must land in
the store.

## Why your applied theme doesn't show in the menu

The plugin currently writes a CSS file to
`<frontend>/src/assets/css/themes/<name>.css` and injects an
`@import` into `<frontend>/src/assets/css/style.css` between sentinel
comments. That import lands in CSS *before* the app boots, so the
custom properties are set on `:root` and the page does pick up the
colors visually.

But:

- The menu reads from `colorPaletteStore.palettes`, which only
  contains palettes that were registered by JSON shape (built-ins
  bundled in `coreColorPalettes.ts` plus customs from settings).
- We never call `addCustomColorPalette()`, never persist a JSON shape
  to `Comfy.CustomColorPalettes`, never update `activePaletteId`.
- `Comfy.ColorPalette` stays at `'dark'` (or whatever was set
  previously), so the picker shows that palette as active.
- Worse: clicking *any* item in the picker calls
  `loadColorPalette(id)`, which calls `loadComfyColorPalette` →
  `rootStyle.setProperty()` — and **overwrites** the variables we set
  via stylesheet. Our theme silently disappears.

So the bug isn't a missing menu entry — it's a fundamental
architectural mismatch. We're playing in the CSS layer; the menu
plays in the data layer; and the data layer wins on every click.

## Where the new app-mode tokens fit (they don't yet)

PR #11317 introduces `--app-mode-go-*`, `--app-mode-stop-*`, and the
`--app-mode-widget-*` family. These are:

- Declared in `src/assets/css/style.css` `:root` (and the
  `.app-mode-themed` class for widget tokens).
- Hard-coded hex values, not derived from any palette.
- Not in `colorPaletteSchema.ts`.
- Not touched by `colorPaletteService.loadColorPalette`.

This is consistent with the PR's own internal note ("a theme system
redesign I will start as a fork this week"). The new layer was
designed for the new App Mode, but the *integration with the existing
palette schema is unfinished*.

## What the community does today

JSON palettes are the lingua franca. Distribution is fragmented across:

- GitHub (most repos): `shahshrey/ComfyUI-themes` (categorized,
  gallery at comfyui-themes.com), `meimeilook/ComfyUI-ColorPalettes`
  (per-node swatch JSONs), `Niutonian/ComfyUI-Niutonian-Themes`,
  `sizzlebop/ComfyUI-Themes-Cyberpunk`, `gmorks/ComfyUI-color-palettes`,
  `Arroz-11/ComfyUI-Linear-Theme` (ships its own runtime editor
  inside a JS extension).
- Civitai: surprisingly active despite being a model host.
  Catppuccin Mocha, Boto's custom theme, Illuminate, Caribbean Light.
- DeviantArt, UserStyles.world (Stylus userscript), Figma Community
  (design source files).

Existing tooling:

- No standalone palette generator was found in any search. The
  closest is the editor bundled inside `ComfyUI-Linear-Theme` — not
  reusable.
- `comfyui-themes.com` is a gallery, not a generator.
- ComfyUI Manager handles JS-extension-style themes but **no
  first-class JSON-only palette installation** — users still
  import-from-file by hand.

Notable gaps:

- **Catppuccin Mocha exists; Latte / Frappé / Macchiato do not.**
- **Tokyo Night, Rose Pine, Gruvbox, Everforest, Kanagawa have no
  ComfyUI ports** despite each having dozens of ports for other
  software. ComfyUI is invisible to those palette projects.
- **No r/unixporn, dotfile-repo, or rice-community presence.** The
  ricing stack is OS chrome (WMs, bars, terminals); ComfyUI hasn't
  crossed over yet.
- The official escape-hatch `ComfyUI/user/<name>/user.css` is broken
  (issues #1999 and #6544 — gets overwritten on update).

## Two integration paths for our generator

### Path A — emit JSON palettes (works today)

Rewrite the plugin's output: instead of a CSS file, build a JSON
object matching `colorPaletteSchema`, then call
`colorPaletteService.addCustomColorPalette(palette, { setActive:
true, persist: true })`.

Result:
- Theme appears in the menu under its `name`.
- Persists across sessions via `Comfy.CustomColorPalettes`.
- Survives palette swaps (clicking another menu entry doesn't wipe
  it).
- Distributable as a single `.json` file, compatible with every
  existing community channel.

Cost:
- We **lose ability to theme the new app-mode tokens** (`--app-mode-*`)
  because the schema doesn't include them. App Mode reverts to its
  hard-coded defaults regardless of palette.

### Path B — extend the schema, then emit JSON (the right long-term fix)

Land a small PR that adds a fourth color group to the palette schema
(name TBD — `app_mode`, `app_mode_base`, or fold under existing
groups). Update:

- `src/schemas/colorPaletteSchema.ts` — add the group, mark optional
  for backwards compat.
- `src/services/colorPaletteService.ts` — add `loadAppModeColorPalette`
  helper that walks the new keys and calls `rootStyle.setProperty`.
- `src/constants/coreColorPalettes.ts` defaults — provide the current
  hard-coded `--app-mode-*` values as the schema defaults so existing
  palettes (which won't include the new group) still get sensible
  values.

Then our generator emits the new schema and everything works:
palettes integrated, app-mode themed, picker correct.

This is also the cleanest long-term resolution to the PR-#11317
internal note about "pending a product/design call on whether to
promote them to semantic tokens or swap them" — the *right* answer
is "they're palette tokens; surface them in the schema."

**Recommended sequencing**: ship Path B (the schema PR) first, then
flip the generator to emit the new schema. Path A is a 1-day stopgap
if the schema PR slips.

## Concrete PR opportunities, in priority order

1. **Schema: add app-mode color group** to `colorPaletteSchema.ts` +
   loader hook in `colorPaletteService.ts` + defaults in
   `coreColorPalettes.ts`. Backwards compatible. **Unblocks
   integration of generator output and any other tool targeting the
   new App Mode tokens.**

2. **File-based palette discovery**. Scan
   `<frontend>/src/assets/palettes/*.json` (or a userland equivalent
   like `<frontend>/user/palettes/`) and merge them into
   `customPalettes` at startup. Lets generators write a file and have
   it appear in the menu without an explicit registration call.

3. **Reload-palettes button** in the Appearance settings panel.
   Triggers re-scan of the discovery directory and re-merge.
   Currently you have to restart the app.

4. **Document the schema and the `addCustomColorPalette` service
   call** as a stable public API. Right now the schema docs say it
   "may change with frontend updates" — fixing that is mostly a
   Zod-version-and-changelog question, not a code change.

5. **Fix the `user.css` overwrite bug** (issues #1999, #6544). The
   fix likely belongs upstream in the comfy-installer or
   workflow-templates side, but the frontend can at minimum *load*
   user.css without writing to it.

6. **Generator-side: emit JSON via Path A** so we can ship something
   that integrates today even without the schema PR.

## Ricing-friendly customization recommendations

ComfyUI is invisible to the major palette projects today. Three
moves that would change that:

- **Build the canonical port adapter.** A small generator that takes
  a standard palette JSON (catppuccin, tokyonight, rose-pine,
  gruvbox, etc. all publish their colors in well-known shapes) and
  emits a ComfyUI palette JSON. Each project gets a one-line
  contribution: a ComfyUI port. ComfyUI ends up in catppuccin.com /
  tokyonight.org / rose-pine.org port directories.

- **Define a "rice manifest" convention.** Single bundle: palette
  JSON + screenshot PNG + a `meta.json` with author, license, source
  palette, install instructions. shahshrey already nudges this with
  `description` and `imageUrl` fields; codify it. A directory of
  these is what r/unixporn and the dotfile community expect.

- **Surface the generator's render_theme_image output as the
  preview.** The 1080×1080 PNG we emit *is* the rice manifest's
  screenshot. Bundle palette JSON + rendered image + name into one
  shareable artifact.

The unixporn lane is open. ComfyUI is one of the most visible
pieces of UI on a creative-AI desktop; it should be themable to
match.
