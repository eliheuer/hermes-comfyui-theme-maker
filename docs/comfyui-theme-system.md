# How ComfyUI's theme system actually works

A practical guide to the existing color-palette system in
ComfyUI_frontend, where our generator currently bypasses it, why your
applied theme doesn't show in the theme menu, and concrete PR-able
improvements. Grounded in the current source on branch
`app-mode-semi-customizable-layout` (PR #11317).

This doc is the load-bearing reference for the PR work happening
alongside this generator: PR #11317 will be updated to fit the
existing theme system, the generator switches to Path A (emit JSON
palettes), and theme-system improvements ship as a separate later PR.

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

## The palette schema

Defined at `src/schemas/colorPaletteSchema.ts` using Zod. Three color
groups, each mapping to a different rendering surface.

```ts
{
  id: string,
  name: string,
  colors: {
    node_slot:      Partial<NodeSlotColors>,      // 16 keys
    litegraph_base: Partial<LiteGraphBaseColors>, // 25 keys
    comfy_base:     Partial<ComfyBaseColors>,     // 18 required + 9 optional
  },
  light_theme?: boolean,
  // .passthrough() — extra fields like `version`, `description`, `imageUrl`
  // from community schemas are preserved.
}
```

`partialColorsSchema` makes every individual key optional within its
group. A palette can override a single key and inherit all the others
from the active "completed" palette
(`DEFAULT_DARK_COLOR_PALETTE` or `DEFAULT_LIGHT_COLOR_PALETTE`).

### The 16 `node_slot` keys (canvas connection types)

```
CLIP, CLIP_VISION, CLIP_VISION_OUTPUT, CONDITIONING, CONTROL_NET,
IMAGE, LATENT, MASK, MODEL, STYLE_MODEL, VAE, NOISE, GUIDER,
SAMPLER, SIGMAS, TAESD
```

These color the dots and connection lines on the graph canvas, one
color per data type. Semantically meaningful — users read connection
type at a glance from color.

### The 25 `litegraph_base` keys (canvas-level node rendering)

Fixed-name colors used by the litegraph canvas internals. Most are
applied as JS properties on `app.canvas` (e.g.
`app.canvas.node_title_color = …`); a subset is also surfaced as CSS
variables for the Vue node renderer.

```
BACKGROUND_IMAGE, CLEAR_BACKGROUND_COLOR,
NODE_TITLE_COLOR, NODE_SELECTED_TITLE_COLOR,
NODE_TEXT_COLOR, NODE_TEXT_HIGHLIGHT_COLOR,
NODE_DEFAULT_COLOR, NODE_DEFAULT_BGCOLOR, NODE_DEFAULT_BOXCOLOR,
NODE_DEFAULT_SHAPE, NODE_BOX_OUTLINE_COLOR,
NODE_BYPASS_BGCOLOR, NODE_ERROR_COLOUR, DEFAULT_SHADOW_COLOR,
WIDGET_BGCOLOR, WIDGET_OUTLINE_COLOR,
WIDGET_TEXT_COLOR, WIDGET_SECONDARY_TEXT_COLOR, WIDGET_DISABLED_TEXT_COLOR,
LINK_COLOR, EVENT_LINK_COLOR, CONNECTING_LINK_COLOR,
BADGE_FG_COLOR, BADGE_BG_COLOR
```

`BACKGROUND_IMAGE` is a base64 PNG (the canvas grid texture) — not a
color but stored in this group. `NODE_DEFAULT_SHAPE` is an enum
(`BOX_SHAPE`/`ROUND_SHAPE`/`CARD_SHAPE`) — also not a color.

### The 18 required + 9 optional `comfy_base` keys (UI chrome)

Applied as plain CSS custom properties on `:root` via
`rootStyle.setProperty('--' + key, value)`
(`colorPaletteService.ts:209-226`).

**Required (18):**
```
fg-color, bg-color,
comfy-menu-bg, comfy-menu-secondary-bg, comfy-input-bg,
input-text, descrip-text, drag-text, error-text,
border-color,
tr-even-bg-color, tr-odd-bg-color,
content-bg, content-fg, content-hover-bg, content-hover-fg,
bar-shadow
```

**Optional (9), with fallback to `var(--palette-${key})` when absent:**
```
bg-img,
contrast-mix-color,
interface-stroke,
interface-panel-surface,
interface-panel-box-shadow, interface-panel-drop-shadow,
interface-panel-hover-surface,
interface-panel-selected-surface,
interface-button-hover-surface
```

The fallback (`colorPaletteService.ts:219-226`) is important: if a
palette doesn't define `interface-stroke`, the loader sets
`--interface-stroke: var(--palette-interface-stroke)`, where
`--palette-interface-stroke` is a design-system default. That gives
palettes a way to "skip" UI surfaces that aren't core to their
identity while still rendering coherently.

**There is no app-mode color group.** That's the schema gap PR #11317
exposes (see "PR #11317 mapping" below).

### The `.passthrough()` extension point

`paletteSchema` uses `.passthrough()` so unknown top-level keys are
preserved through validation. Community extensions in the wild:

- `version: 102` — schema version marker, used by shahshrey's pack.
- `description: "..."` — free-form description, used by shahshrey.
- `imageUrl: "/popular/dracula.png"` — preview image relative path,
  used by shahshrey.

The `imageUrl` field is what we'd want our `render_theme_image`
output to populate — a generator emitting palettes alongside their
PNG previews would set this and ship the bundle as one artifact.

## State, persistence, and the loader

### Store

`src/stores/workspace/colorPaletteStore.ts`:

- `customPalettes` — in-memory ref of imported customs
  (`Record<id, Palette>`).
- `activePaletteId` — string ref, the currently-applied id.
- `palettesLookup` — computed: `CORE_COLOR_PALETTES ∪ customPalettes`.
- `palettes` — computed list, used by the picker UI.

### Settings persistence

`src/constants/coreSettings.ts`:

- `Comfy.ColorPalette` (~line 950) — active palette id (default
  `'dark'`). Hidden setting.
- `Comfy.CustomColorPalettes` (~line 963) — dict of imported customs
  (default `{}`). Hidden setting.

A legacy migration strips the `custom_` prefix that older versions
prepended to user palette ids (`coreSettings.ts:956-960`).

### Bootstrap flow

1. App start → `settingStore.load()` (`bootstrapStore.ts:34`) fetches
   settings from backend (`api.getSettings()`).
2. `GraphCanvas.vue:566-568` reads `Comfy.CustomColorPalettes` from
   settings and merges into `colorPaletteStore.customPalettes`.
3. `GraphCanvas.vue:378-382` — watcher on
   `settingStore.get('Comfy.ColorPalette')` triggers
   `colorPaletteService.loadColorPalette(id)` whenever the active id
   changes (or on first load).
4. Bidirectional sync: a separate watcher
   (`GraphCanvas.vue:399-404`) writes `activePaletteId` back to
   `Comfy.ColorPalette` settings whenever the store is updated.

### Loader chain

`src/services/colorPaletteService.ts:249-270` →
`loadColorPalette(id)`:

1. Fetch palette from `palettesLookup` by id.
2. Merge with `DEFAULT_DARK_COLOR_PALETTE` /
   `DEFAULT_LIGHT_COLOR_PALETTE` to fill any missing keys.
3. Apply five sub-loaders in order:
   - `loadLinkColorPalette` — sets LiteGraph
     `default_connection_color_byType` (slot dots + lines).
   - `loadLiteGraphColorPalette` — sets canvas object properties
     (`app.canvas.node_title_color = …` etc.).
   - `loadLitegraphForVueNodes` — injects `--component-node-*` CSS
     variables for the Vue node renderer.
   - `loadLinkColorPaletteForVueNodes` — injects
     `--color-datatype-{type}` CSS variables.
   - `loadComfyColorPalette` — injects `comfy_base` keys as CSS
     variables on `:root`.

### UI binding

`src/components/sidebar/ComfyMenuButton.vue:182-194` builds the menu
from `colorPaletteStore.palettes`. Each palette → one menu item; the
active one shows a checkmark. Clicking calls
`colorPaletteService.loadColorPalette(id)`. **The picker source of
truth is the store — not stylesheets, not files on disk. Anything
that wants to be in the picker must land in the store.**

## Bootstrap timeline (corrected and verified)

The actual sequence at app startup, traced from `main.ts` to
first-paint with the active palette applied:

1. **`main.ts`** — `useBootstrapStore().startStoreBootstrap()` fires
   *before* `app.mount('#vue-app')`. PrimeVue is installed with
   `darkModeSelector: '.dark-theme, :root:has(.dark-theme)'`
   (workaround for [primevue/primevue#5515](https://github.com/primefaces/primevue/issues/5515)).
2. **`bootstrapStore.loadAuthenticatedStores()`** — calls
   `settingStore.load()`, which `await`s `api.getSettings()` and
   populates `settingStore.settingValues`. Both `Comfy.ColorPalette`
   (string) and `Comfy.CustomColorPalettes` (record) are now in
   memory.
3. **`app.mount('#vue-app')`** — Vue components start mounting.
4. **`GraphView.vue:137-154`** — `watch(() =>
   colorPaletteStore.completedActivePalette, ..., { immediate: true })`
   fires. Toggles `.dark-theme` class on `document.body`. Reports
   the chosen text color to the Electron host (desktop only).
   - **At this moment, `customPalettes` is still `{}`.** If the
     user's saved active id refers to a custom palette, it will
     not yet resolve in `palettesLookup` — so the watcher reads
     the default palette and may toggle the wrong `.dark-theme`
     state briefly.
5. **`GraphCanvas.vue:566-568`** — inside `onMounted`,
   `colorPaletteStore.customPalettes = settingStore.get('Comfy.CustomColorPalettes')`
   hydrates the store from settings.
6. **`palettesLookup` recomputes** with the user's customs included.
   `completedActivePalette` now resolves correctly.
7. **The watcher in step 4 fires again** with the corrected palette.
   `.dark-theme` is set to its final value.
8. **`loadColorPalette(id)`** runs the five-stage loader chain
   described above; CSS variables on `:root`, canvas properties,
   and node-data-type colors all become correct.
9. **First paint with the right palette.**

> **Race-condition / FOUC finding.** Steps 4–7 are a real gap. If
> the active palette is a *custom* one, the page paints with the
> default-dark palette for a frame or two before the custom is
> applied. Easy to reproduce: import a custom palette, set it
> active, hard reload. Visible flash. Worth noting as one of the
> "address #11048" PRs (move custom-palette hydration into the
> bootstrap chain instead of `GraphCanvas.onMounted`).

## Light/dark switching

`.dark-theme` lives on **`document.body`** (not `:root`). The class
is toggled by the watcher at `src/views/GraphView.vue:137-154`
listening to `colorPaletteStore.completedActivePalette.light_theme`:

```ts
watch(
  () => colorPaletteStore.completedActivePalette,
  (newTheme) => {
    if (newTheme.light_theme) {
      document.body.classList.remove('dark-theme')
    } else {
      document.body.classList.add('dark-theme')
    }
    // ...electron host theme update
  },
  { immediate: true }
)
```

There is **no separate dark-mode toggle** in settings — palette
choice IS the dark/light choice. A palette is "light" if its
`light_theme: true` flag is set in JSON. Picking "Light" or "Github"
removes the class; picking any other built-in adds it.

PrimeVue's dark-mode CSS scopes to `.dark-theme, :root:has(.dark-theme)`
(see `src/main.ts`). So PrimeVue's `--p-*` tokens swap between dark
and light values automatically when the class toggles. The palette
JSON's `comfy_base` keys then layer on top via `:root.style.setProperty`.

## The `--palette-*` fallback namespace

When `loadComfyColorPalette` (`colorPaletteService.ts:209-226`) sees
that an *optional* `comfy_base` key is missing from the active
palette, it sets the corresponding CSS variable to a `var(--palette-${key})`
reference instead of leaving it unset.

The `--palette-*` defaults are declared at
`packages/design-system/src/css/style.css:288-312`, in `:root` only:

```css
:root {
  --palette-contrast-mix-color: #fff;
  --palette-interface-panel-surface: var(--comfy-menu-bg);
  --palette-interface-stroke: color-mix(
    in srgb,
    var(--interface-panel-surface) 75.5%,
    var(--contrast-mix-color)
  );
  --palette-interface-panel-box-shadow: 1px 1px 8px 0 rgb(0 0 0 / 0.4);
  --palette-interface-panel-drop-shadow: 1px 1px 4px rgb(0 0 0 / 0.4);
  --palette-interface-panel-hover-surface: color-mix(
    in srgb, var(--interface-panel-surface) 92.5%,
    var(--contrast-mix-color)
  );
  --palette-interface-panel-selected-surface: color-mix(/* ... */);
  --palette-interface-button-hover-surface: color-mix(/* ... */);
}
```

These are **derivations** from other palette-aware variables
(`--comfy-menu-bg`, `--interface-panel-surface`, `--contrast-mix-color`).
That's intentionally clever: when the active palette swaps and
`--comfy-menu-bg` changes, the fallback values automatically follow,
because they're computed via `color-mix` of palette-aware inputs.

> **Light-mode fallback gap.** The `--palette-*` definitions are not
> redefined in `.dark-theme`, but their *inputs* are palette-aware
> via the cascade. So in practice the fallbacks track the palette
> correctly. Worth verifying empirically — could be a subtle theming
> bug if any of the inputs (`--contrast-mix-color: #fff`) aren't
> palette-aware.

## The four overlapping color systems (per issue #11048)

The team has **already filed an audit issue** acknowledging the
fragility we're working around:
[`Comfy-Org/ComfyUI_frontend#11048`](https://github.com/Comfy-Org/ComfyUI_frontend/issues/11048)
— *"4 layered color systems create fragile overrides"*. Quote from
the issue:

> "The color palette service dynamically overrides CSS variables set
> by the design system, which can be fragile. As PrimeVue is
> migrated away, one layer will eventually be removed. Consider
> having the palette system generate Tailwind-compatible tokens
> directly."

The four layers, in order of cascade:

| Layer | Where | Mechanism |
|---|---|---|
| 1. PrimeVue Aura preset | `src/main.ts:43-100` | PrimeVue's own CSS, switched via `.dark-theme` selector. Provides `--p-*` tokens. |
| 2. Design-system @theme | `packages/design-system/src/css/style.css` | Tailwind 4 `@theme` block. Semantic tokens reference `--p-*` and palette-set values. |
| 3. Color palette JSON | `colorPaletteService.loadComfyColorPalette` | Runtime `:root.style.setProperty('--key', value)` overrides at app boot and on palette change. |
| 4. LiteGraph CSS | `src/lib/litegraph/public/css/litegraph.css` | Canvas-internal styling, partly themed via palette JS properties. |

**Long-term direction signaled by the team:** PrimeVue (layer 1) is
being phased out as part of vue-migration. The palette system
(layer 3) should eventually emit Tailwind tokens directly into the
design-system's `@theme` rather than via runtime
`style.setProperty`. This is the architectural target reviewers
will measure PRs against.

## Test coverage

`browser_tests/tests/colorPalette.spec.ts` is the only palette-
specific test file. It covers:

- ✓ Custom palette loading via settings.
- ✓ Custom palette application via `addCustomColorPalette()`.
- ✓ Legacy `custom_` prefix migration (`coreSettings.ts:956-960`).
- ✓ Light-theme rendering (visual / `light_theme` flag).
- ✓ Node-color opacity adjustments persist across theme changes.
- ✓ Node colors aren't serialized into workflow JSON.

Coverage gaps:

- ✗ Partial-palette merge: missing optional keys → `--palette-*`
  fallback chain.
- ✗ First-run scenario: no `Comfy.ColorPalette` setting yet.
- ✗ Custom-palette hydration race: the FOUC window between
  GraphView.vue:137 and GraphCanvas.vue:566.
- ✗ `.dark-theme` class toggle behavior in isolation (only covered
  indirectly via light_theme rendering tests).
- ✗ PrimeVue `--p-*` ↔ palette interaction when palette swaps (do
  PrimeVue tokens actually update?).

Recent palette-system git history (last 90 days): no commits to
`colorPaletteService.ts`, `colorPaletteStore.ts`,
`colorPaletteSchema.ts`, `coreColorPalettes.ts`, or
`src/assets/palettes/*.json`. The system is stable but neglected.

## Why our `@import` bypass is invisible (and gets erased)

Our generator currently writes
`<frontend>/src/assets/css/themes/<name>.css` and injects an `@import`
into `<frontend>/src/assets/css/style.css` between sentinel comments.
That import lands *before* the app boots, so the custom properties
are set on `:root` and the page picks up the colors visually.

But:

- The menu reads from `colorPaletteStore.palettes`, which only
  contains palettes registered via JSON shape (built-ins +
  `addCustomPalette()`-d customs). We never call that.
- We never persist anything to `Comfy.CustomColorPalettes`.
- We never update `activePaletteId`. It stays at `'dark'`.
- Worse: clicking *any* item in the picker calls `loadColorPalette` →
  `loadComfyColorPalette` → `rootStyle.setProperty()`, which
  **overwrites** the variables our stylesheet set. Our theme silently
  disappears on the next palette click.

So the bug isn't a missing menu entry — it's an architectural
mismatch. We're playing in the CSS layer; the menu plays in the data
layer; and the data layer wins on every click.

## PR #11317 token mapping

PR #11317 introduces these custom properties at `src/assets/css/style.css`
`:root` and `.app-mode-themed`:

**Action buttons (Run / Stop):**
```
--app-mode-go-bg, --app-mode-go-bg-hover, --app-mode-go-border
--app-mode-stop-bg, --app-mode-stop-bg-hover, --app-mode-stop-border
```

**Widget surface:**
```
--app-mode-widget-bg, --app-mode-widget-border,
--app-mode-widget-border-focus, --app-mode-widget-button-hover-bg,
--app-mode-widget-selection-bg
```
(plus three lengths — `--app-mode-widget-min-h`,
`--app-mode-widget-input-pad-x`, `--app-mode-widget-textarea-pad` —
which aren't theme-relevant and stay as hard-coded sizes.)

**Mapping each color token to existing palette / semantic equivalents:**

| App-mode token | Closest existing token | Notes |
|---|---|---|
| `--app-mode-go-bg` | *(no equivalent)* | New semantic: primary destructive-positive action. The palette has no notion of action buttons. |
| `--app-mode-go-bg-hover` | *(no equivalent)* | Derive: `color-mix(in srgb, var(--app-mode-go-bg) 80%, white)`. |
| `--app-mode-go-border` | *(no equivalent)* | Derive: `color-mix(in srgb, var(--app-mode-go-bg) 80%, black)`. |
| `--app-mode-stop-bg` | `var(--error-text)` (loosely) | `error-text` is a foreground color, not a background. Palette has no stop/danger action color. |
| `--app-mode-stop-bg-hover` | *(no equivalent)* | Same derive pattern as go. |
| `--app-mode-stop-border` | *(no equivalent)* | Same. |
| `--app-mode-widget-bg` | `var(--comfy-input-bg)` | Direct semantic match — both are "widget input surface." |
| `--app-mode-widget-border` | `var(--border-color)` | Direct match. |
| `--app-mode-widget-border-focus` | *(no equivalent)* | Derive: `color-mix(in srgb, var(--border-color) 50%, var(--fg-color))`. |
| `--app-mode-widget-button-hover-bg` | `var(--content-hover-bg)` | Loosely. |
| `--app-mode-widget-selection-bg` | *(no equivalent)* | New: text selection background. Browsers default to system blue; palette has no override. |

**The pattern that emerges:** widget tokens map cleanly to existing
palette keys (`comfy-input-bg`, `border-color`, `content-hover-bg`).
Action-button tokens (Run / Stop) and widget-focus / selection
states are **new semantic concepts** the palette schema doesn't yet
express.

### Recommended PR #11317 update strategy

Two viable approaches; pick based on how much App Mode visual
identity matters vs. shipping speed.

**Option 1 (cleanest, recommended for merge):** drop the
`--app-mode-*` color tokens entirely. In `src/assets/css/style.css`,
replace each usage:

```css
/* Before */
.app-mode-themed input { background-color: var(--app-mode-widget-bg); }

/* After */
.app-mode-themed input { background-color: var(--comfy-input-bg); }
```

For Run/Stop buttons (no palette equivalent), inline known good
green/red values now and add a note that the next PR will surface
them as palette tokens. Or use semantic `color-mix` derivations from
existing palette colors.

This makes App Mode **automatically themed by every palette in the
menu** — Dark, Light, Arc, Nord, Solarized, Github, plus any custom
the user imports. Zero new tokens, zero schema changes, palette
system stays clean.

**Option 2 (faster, leaves schema cleanup to the follow-up PR):**
keep the `--app-mode-*` tokens but **define them with `color-mix`
derivations of palette tokens** at `:root`:

```css
:root {
  --app-mode-widget-bg: var(--comfy-input-bg);
  --app-mode-widget-border: var(--border-color);
  --app-mode-go-bg: #279252;  /* TODO: surface in palette schema */
  /* ... */
}
```

App Mode tracks the active palette automatically (because the new
tokens dereference palette tokens), but the variables themselves
remain. The follow-up PR can then replace each `--app-mode-*` with
its palette-side equivalent and remove the indirection.

Either way: **stop hardcoding raw hex values in the App Mode token
declarations**. That's what makes the new code "outside" the palette
system. Dereferencing palette tokens brings App Mode back inside.

## Path A: switching the generator to JSON palettes

This unblocks "themes appear in the menu" without waiting for the
schema PR. Steps:

1. **Drop the `_render_css` / `_resolve_named_theme` /
   `_load_theme_groups` machinery for theme files.** Stop writing
   `<frontend>/src/assets/css/themes/<name>.css` entirely.
2. **`write_comfyui_theme` rewrites to emit a palette JSON.** Output
   path is wherever, but the canonical location for the agent's
   reference is the user's local cache. The shape:
   ```json
   {
     "id": "campfire-warm",
     "name": "campfire-warm (hermes-comfyui-theme-maker)",
     "light_theme": false,
     "description": "Generated <date> from prompt: <mood prompt>",
     "imageUrl": "<absolute path to render_theme_image PNG>",
     "colors": {
       "node_slot": { /* palette anchors mapped to slot types */ },
       "litegraph_base": { /* anchors mapped to canvas */ },
       "comfy_base": { "fg-color": "...", "bg-color": "...", ... }
     }
   }
   ```
3. **`apply_comfyui_theme` rewrites to call `addCustomColorPalette`**
   on the running ComfyUI's HTTP API. ComfyUI's settings API
   (`/api/settings`) is the persistence layer; PUTting to
   `Comfy.CustomColorPalettes` (or whatever the public API is called)
   is the integration point. Verify by hitting `GET /api/settings`
   and seeing the palette show up.
4. **Update `generate_mood_image` mapping logic** in the SKILL.md.
   The agent now has to map the extracted palette onto a
   palette-schema JSON, not a flat token-override dict. The
   established `comfy_base` keys (`bg-color` = darkest, `fg-color` =
   lightest, `comfy-menu-bg` = bg-darker, etc.) become the targets.
5. **Drop the `frontend_path` requirement.** Talking to ComfyUI's
   HTTP API doesn't need a filesystem path. (Though we still need it
   if Path A also writes a JSON file for the user to import manually
   as a fallback.)
6. **Drop the `style.css` modification.** No more sentinel block, no
   more `@import`. The plugin no longer writes into
   ComfyUI_frontend's source tree.
7. **Theme menu appears with the new entry.** Active palette shows
   as the new theme. Switching palettes in the menu works correctly
   — clicking another palette doesn't erase ours; clicking ours back
   restores it.

The token inventory in `token_inventory.py` becomes wrong (it lists
the hyphen-cased palette-layer tokens like `color-charcoal-800`; the
schema wants `comfy_base` keys like `bg-color`). Replace it with the
canonical 18+9 `comfy_base` keys, the 16 `node_slot` keys, and the
24 `litegraph_base` color keys.

This is a substantial rewrite of `tools.py` (roughly 50% of it
becomes irrelevant or different). Worth it: the result is
distributable as a `.json` file, compatible with every existing
ComfyUI theme channel, and shows up in the menu as expected.

## What the community does today

JSON palettes are the lingua franca. Distribution is fragmented
across a half-dozen channels.

- **GitHub** is the largest. Topic tag:
  [`comfyui-theme`](https://github.com/topics/comfyui-theme).
  Notable repos:
  - [`shahshrey/ComfyUI-themes`](https://github.com/shahshrey/ComfyUI-themes)
    — categorized (Dark / Light / Vibrant / Nature / Gradient /
    Monochrome / Popular). Companion gallery at
    [comfyui-themes.com](https://www.comfyui-themes.com/). Uses the
    `version` / `description` / `imageUrl` schema extension.
  - [`shahshrey/ComfyUI-ColorPalettes`](https://github.com/shahshrey/ComfyUI-ColorPalettes)
  - [`meimeilook/ComfyUI-ColorPalettes`](https://github.com/meimeilook/ComfyUI-ColorPalettes)
    (per-node Material/FlatUI swatches; not whole-UI themes — search
    results conflate them with palette themes).
  - [`Niutonian/ComfyUI-Niutonian-Themes`](https://github.com/Niutonian/ComfyUI-Niutonian-Themes)
    (10 themes, Alt+1..0 hotkeys; uses a non-canonical top-level
    shape `{ node_bg, border_color, corner_radius, glass: false }`).
  - [`sizzlebop/ComfyUI-Themes-Cyberpunk`](https://github.com/sizzlebop/ComfyUI-Themes-Cyberpunk)
    — Cyber Noir / Cyber Raspberry / Matrix Glow / Toxic Neon / Neon
    Pulse.
  - [`sizzlebop/ComfyUI-Themes-Nature`](https://github.com/sizzlebop/ComfyUI-Themes-Nature)
  - [`gmorks/ComfyUI-color-palettes`](https://github.com/gmorks/ComfyUI-color-palettes)
    — Coral Dark / Emerald Dark / Golden Contrast.
  - [`Arroz-11/ComfyUI-Linear-Theme`](https://github.com/Arroz-11/ComfyUI-Linear-Theme)
    — Linear/Vercel/Raycast-inspired. Ships a built-in editor for
    live customization (closest analog to a generator that exists,
    bundled inside one specific theme's JS extension).
- **Civitai** — surprisingly active for a model host:
  - [Illuminate](https://civitai.com/models/271238/illuminate-a-comfyui-theme)
  - [Catppuccin Mocha by neuromask](https://civitai.com/models/315515/comfyui-catppuccin-mocha-color-palette-comfyui-skin)
    (Mocha only — Latte / Frappé / Macchiato don't exist).
  - [Boto's Custom Theme](https://civitai.com/models/496482/botos-comfyui-custom-theme)
  - [ComfyUI Themes collection](https://civitai.com/models/1626419/comfyui-themes)
- **DeviantArt** — [nuforms' Catppuccin Mocha
  palette](https://www.deviantart.com/nuforms/art/ComfyUI-Catppuccin-Mocha-Color-Palette-1023439541).
- **UserStyles.world** —
  [comfyui custom css](https://userstyles.world/style/14049/comfyui-custom-css)
  (the only Stylus-style distribution found).
- **Figma Community** —
  [ComfyUI Color Palettes](https://www.figma.com/community/file/1346736809617182452/comfyui-color-palettes)
  (design source, not a runtime artifact).
- **ComfyUI Manager** — installs the JS-extension-style themes
  (Niutonian, Linear) but **does not first-class JSON-only palettes**.
  Users still import JSON by hand through Settings.

### Install / load mechanics

Two paths, well-documented:

1. **Settings → Appearance → Color Palette → Import**, pick the
   `.json`. Themes can also be exported the same way — the
   recommended starting point is to export the active palette and
   modify, since the schema "may change with frontend updates" per
   the official docs.
2. **Drop into `ComfyUI/web/data/`** and restart. The file shows up
   in the picker. (This is file-based discovery, unlike the
   import-into-settings approach.)

### Notable gaps in the existing ecosystem

- **Catppuccin Mocha exists; Latte / Frappé / Macchiato do not.**
- **Tokyo Night, Rose Pine, Gruvbox, Everforest, Kanagawa have no
  ComfyUI ports** despite each having dozens of ports for other
  software. ComfyUI is invisible to those palette projects.
- **Zero r/unixporn / dotfile-repo / rice-community presence.** The
  ricing stack is OS chrome (WMs, bars, terminals); ComfyUI hasn't
  crossed over yet. This is an open lane.
- **No standalone palette generator exists.** The closest is the
  editor inside `ComfyUI-Linear-Theme` — bundled in one theme's JS,
  not reusable. comfyui-themes.com is a gallery, not a generator.
- **No "rice manifest" convention.** Sharing a theme is a JSON file;
  pairing it with a screenshot, author metadata, or one-line install
  command is ad-hoc.
- **`user.css` escape hatch is broken.** Anything in
  `ComfyUI/user/<name>/user.css` gets overwritten on update —
  [issue #1999](https://github.com/comfyanonymous/ComfyUI/issues/1999),
  [issue #6544](https://github.com/comfyanonymous/ComfyUI/issues/6544).

## PR opportunities, in priority order

1. **Update PR #11317 to use existing palette tokens.** Drop or
   dereference the `--app-mode-*` color tokens (per the mapping
   table above). Unblocks merging the App Mode redesign without
   forking the theme system.

2. **Schema PR: add app-mode color group** to
   `colorPaletteSchema.ts`. Add `app_mode` (or fold under existing
   groups) covering action buttons (`go-bg`, `stop-bg`, hover and
   border variants) and widget focus / selection states. Update
   `colorPaletteService` with a loader hook. Provide defaults in
   `coreColorPalettes.ts` so existing palettes (Dark, Light, Arc,
   Nord, Solarized, Github) get sensible action-button colors
   without explicit changes.

3. **File-based palette discovery** that scans
   `<frontend>/src/assets/palettes/*.json` (already loaded as
   built-ins) and a userland equivalent (e.g.
   `<frontend>/user/palettes/`) and merges into `customPalettes` at
   startup. Drop a JSON, get a menu entry. Generators write a file;
   the menu picks it up.

4. **Reload-palettes button** in the Appearance settings panel.
   Triggers re-scan of the discovery directory and re-merge.
   Currently you have to restart the app.

5. **Document the schema and `addCustomColorPalette` as a stable
   public API.** Right now the schema docs say it "may change with
   frontend updates"; that's the opposite of what tool authors need.
   Mostly a Zod-version-and-changelog question.

6. **Fix `user.css` overwrite** (#1999, #6544). Likely upstream in
   the comfy-installer / workflow-templates side, but the frontend
   can at minimum *load* user.css without writing to it.

## Ricing / unixporn recommendations

Three moves to make ComfyUI visible to the ricing community:

- **Build a port adapter for the standard palette projects.** A
  small generator that takes a published palette JSON (catppuccin,
  tokyonight, rose-pine, gruvbox, everforest, kanagawa all expose
  their colors in well-known shapes) and emits a ComfyUI palette
  JSON. Each project gets a one-line contribution: a ComfyUI port.
  ComfyUI ends up in their port directories.

- **Define a "rice manifest" convention.** Single bundle: palette
  JSON + screenshot PNG + a `meta.json` with author, license, source
  palette, install instructions. shahshrey already nudges toward
  this with `description` and `imageUrl`; codify it. A directory of
  these is what r/unixporn and the dotfile community expect.

- **Surface our `render_theme_image` output as the manifest's
  preview.** The 1080×1080 PNG we emit *is* the rice manifest's
  screenshot. Bundle palette JSON + rendered image + name into one
  shareable artifact.

The ricing lane is open. ComfyUI is one of the most visible pieces
of UI on a creative-AI desktop; it should be themable to match.

## Appendix A: relevant source files (paths in ComfyUI_frontend)

| File | Purpose |
|---|---|
| `src/schemas/colorPaletteSchema.ts` | Zod schemas for palette validation. |
| `src/constants/coreColorPalettes.ts` | Hard-coded 6 built-in palettes. |
| `src/assets/palettes/{dark,light,arc,nord,solarized,github}.json` | The built-in palette JSON files. |
| `src/stores/workspace/colorPaletteStore.ts` | Pinia store: customPalettes, activePaletteId, palettesLookup. |
| `src/services/colorPaletteService.ts` | Loader chain (lines 209-270 are the meat). |
| `src/components/sidebar/ComfyMenuButton.vue:182-194` | Theme menu UI. |
| `src/components/graph/GraphCanvas.vue:377-404, 566-568` | Bootstrap merge + bidirectional setting↔store sync. |
| `src/constants/coreSettings.ts:950-963` | `Comfy.ColorPalette` and `Comfy.CustomColorPalettes` setting definitions. |
| `src/assets/css/style.css` | App-mode tokens introduced by PR #11317. |
| `packages/design-system/src/css/style.css` | Semantic-layer tokens that reference the palette via var(). |
| `packages/design-system/src/css/_palette.css` | Foundational palette ramps (charcoal, smoke, etc.) — different namespace from the JSON palette schema. |

## Appendix B: open issues and known bugs

**Theme-system architectural** (Comfy-Org/ComfyUI_frontend):
- [`#11048`](https://github.com/Comfy-Org/ComfyUI_frontend/issues/11048)
  — *"4 layered color systems create fragile overrides"*. The
  umbrella issue. Filed by the team's `audit-code` skill, labels
  `audit:conflicting`, `area:vue-migration`. Future-direction note:
  palette should generate Tailwind tokens directly; PrimeVue layer
  is being phased out.
- [`#2153`](https://github.com/Comfy-Org/ComfyUI_frontend/issues/2153)
  — *"Color Palette system cannot distinguish between original and
  previously modified Palettes"*. Concrete bug related to the legacy
  `custom_` migration path.
- [`#1363`](https://github.com/Comfy-Org/ComfyUI_frontend/issues/1363)
  — *"[DevTask] Move colorPalettes to core"*. Long-since-closed task
  that explains why palette infrastructure is in the frontend
  package today.

**`user.css` / runtime CSS escape hatches** (comfyanonymous/ComfyUI):
- [`#1999`](https://github.com/comfyanonymous/ComfyUI/issues/1999)
  — `user.css` gets overwritten on update.
- [`#6544`](https://github.com/comfyanonymous/ComfyUI/issues/6544)
  — same root cause, more recent.
- [`#2328`](https://github.com/comfyanonymous/ComfyUI/discussions/2328)
  — Kitchen-ComfyUI discussion; full UI replacement style precedent.

## Appendix C: distribution channels (URL list)

- [github.com/topics/comfyui-theme](https://github.com/topics/comfyui-theme)
- [github.com/shahshrey/ComfyUI-themes](https://github.com/shahshrey/ComfyUI-themes)
- [github.com/shahshrey/ComfyUI-ColorPalettes](https://github.com/shahshrey/ComfyUI-ColorPalettes)
- [github.com/meimeilook/ComfyUI-ColorPalettes](https://github.com/meimeilook/ComfyUI-ColorPalettes)
- [github.com/Niutonian/ComfyUI-Niutonian-Themes](https://github.com/Niutonian/ComfyUI-Niutonian-Themes)
- [github.com/sizzlebop/ComfyUI-Themes-Cyberpunk](https://github.com/sizzlebop/ComfyUI-Themes-Cyberpunk)
- [github.com/sizzlebop/ComfyUI-Themes-Nature](https://github.com/sizzlebop/ComfyUI-Themes-Nature)
- [github.com/gmorks/ComfyUI-color-palettes](https://github.com/gmorks/ComfyUI-color-palettes)
- [github.com/Arroz-11/ComfyUI-Linear-Theme](https://github.com/Arroz-11/ComfyUI-Linear-Theme)
- [comfyui-themes.com](https://www.comfyui-themes.com/) (gallery)
- [civitai.com/models/271238](https://civitai.com/models/271238/illuminate-a-comfyui-theme)
- [civitai.com/models/315515](https://civitai.com/models/315515/comfyui-catppuccin-mocha-color-palette-comfyui-skin)
- [civitai.com/models/496482](https://civitai.com/models/496482/botos-comfyui-custom-theme)
- [docs.comfy.org/interface/appearance](https://docs.comfy.org/interface/appearance)
  (official format docs)
- [comfyui-wiki.com/en/interface/settings/appearance](https://comfyui-wiki.com/en/interface/settings/appearance)
