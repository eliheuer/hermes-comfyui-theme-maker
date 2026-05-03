# ComfyUI Theme Maker

Generate a cohesive ComfyUI frontend theme from a natural-language description.
Output is a CSS custom-property override file written into the user's local
ComfyUI_frontend checkout, where Vite HMR picks it up live.

## When to use this skill

The user says something like:

- "Make ComfyUI dark and synthwave."
- "Theme it like a 90s terminal."
- "Generate a high-contrast accessible theme."
- "Re-skin the app with warm neutrals and a gold accent."

If the user wants anything other than a recoloring (layout, typography
beyond the layout text scale, component restructure), this skill is not the
right fit.

## Workflow

1. **Always call `list_comfyui_tokens` first.** Pass `layer="all"`. The
   response contains every token you can override, plus its current value
   and a short description. Do not invent token names — only override what
   appears in the response.
2. **Decide the palette intent.** From the user's description, pick:
   - **Mode** — dark, light, or either. Default to dark when the user is
     vague; that is the prevailing ComfyUI environment.
   - **Color scheme** — monochromatic, analogous, complementary, triadic.
   - **Accent hue** — the dominant non-neutral.
3. **Map intent to concrete hex values.** Apply these heuristics:
   - The `charcoal` ramp (100 → 800) is the dark-mode neutral spine. Keep
     it monotonically darkening; the rendered lightness should step
     evenly. `charcoal-800` is the darkest (typically the primary
     background); `charcoal-100` is the lightest (high-contrast text).
   - The `smoke` ramp is the light-mode neutral spine, same shape.
   - For dark themes you may leave the `smoke` ramp at defaults (it will
     not visually appear in dark mode).
   - `coral`, `gold`, `jade`, `azure`, `magenta`, `ocean` are accent
     ramps. If you change an accent's hue, retune all steps so
     hover/active states stay coherent (lower numbers lighter, higher
     darker — match the existing ramp shape).
   - Run/Stop colors (`app-mode-go-*`, `app-mode-stop-*`) are hard-coded
     hex in PR #11317 — always override them explicitly when theming the
     new App Mode. Keep `bg-hover` lighter than `bg`; `border` darker.
4. **Call `write_comfyui_theme`.** Pass a slug `name` and a flat
   `overrides` dict of `{token-name: value}`. Names omit the leading
   `--`. Values must be concrete (hex, rgb, rgba), not `var()` references.
5. **Call `apply_comfyui_theme`.** This swaps the active theme via a
   single `@import` line in the frontend's `style.css`, between sentinel
   comments. Idempotent — only one theme active at a time.
6. **Briefly explain what you did.** One short paragraph: mode, scheme,
   accent, any notable trade-offs. The user can then iterate ("warmer",
   "less saturated", "more contrast").

## Token taxonomy

The frontend has three layered token sources:

- **Palette** (`_palette.css`) — raw color ramps: `charcoal-*`, `smoke-*`,
  `ash-*`, `electric-*`, `sapphire-*`. Overriding these cascades through
  every semantic token in the design system.
- **Extended palette + layout** (`design-system/style.css`) — additional
  accent ramps (`coral-*`, `gold-*`, `azure-*`, etc.) and layout color
  tokens (`color-layout-*`).
- **App-mode** (`src/assets/css/style.css`, PR #11317) —
  `app-mode-go-*` and `app-mode-stop-*` Run/Stop button colors. These
  must be overridden directly.

Most themes only need ~20 overrides total: 6–10 charcoal/smoke neutrals,
1–2 accent ramps (3 steps each), and the 6 app-mode go/stop tokens.

## How the cascade works (and why you only override the palette)

The frontend uses a two-step cascade:

- **Palette layer** declares raw color ramps at `:root` (e.g.
  `--color-charcoal-800: #171718`).
- **Semantic layer** declares semantic tokens that reference the palette,
  with different references in `:root` (light mode) and `.dark-theme`
  (dark mode). For example: `.dark-theme { --base-background:
  var(--color-charcoal-800) }` vs `:root { --base-background:
  var(--color-white) }`.

When the user toggles light/dark, the *semantic tokens* swap which
palette ramp they read from. So:

- A palette override of `--color-charcoal-800` automatically applies in
  **dark mode** (every semantic token in `.dark-theme` resolves to the
  new value) and is **invisible in light mode** (light-mode semantic
  tokens read `smoke-*` instead).
- A palette override of `--color-smoke-800` is the mirror: visible in
  light mode, invisible in dark.

**Always override at the palette layer, never the semantic layer.** This
is why the user's existing dark/light toggle keeps working through your
theme.

Practical consequence:

- Theme intended for **dark mode** → override the `charcoal-*` ramp.
- Theme intended for **light mode** → override the `smoke-*` ramp.
- Theme that should work in both → override both.

Accents (`coral`, `gold`, `jade`, `azure`, `magenta`, `ocean`) and
app-mode tokens are mode-independent — overrides apply everywhere.

## Design heuristics

- **Contrast first.** Background-to-foreground luminance ratio should
  exceed 7:1 for body text on neutrals. When in doubt, choose darker
  backgrounds and lighter text.
- **One accent.** Don't introduce two competing high-saturation hues. The
  brand yellow (`electric-400`) and brand blue (`sapphire-700`) can stay
  as is unless the user explicitly wants brand replacement.
- **Match modes.** Dark theme → the charcoal ramp does the heavy lifting.
  Light theme → the smoke ramp does. The other ramp can stay at default.
- **Run = green, Stop = red.** Overriding `app-mode-go-*` to non-green or
  `app-mode-stop-*` to non-red is allowed but warn the user it weakens
  the safety affordance.

## Minimum viable override set

For most themes, twelve to twenty overrides is enough. Anchor on this
shape and only deviate when the user's request demands more.

**Dark-mode theme (~17 tokens):**

- `color-charcoal-100` through `color-charcoal-800` — all 8 steps of the
  neutral spine.
- One accent ramp, all steps. For example `color-azure-300/400/600`,
  or `color-magenta-300/700`, or `color-coral-500/600/700`.
- All six `app-mode-go-*` and `app-mode-stop-*` tokens.

**Light-mode theme (~17 tokens):**

- `color-smoke-100` through `color-smoke-800` — 8 steps.
- `color-white` if the base background should not be pure white.
- One accent ramp.
- All six app-mode tokens.

Going past ~20 overrides usually re-introduces the inconsistencies the
design system was built to prevent.

## Failure modes to avoid

- Don't include `--` in token names passed to `write_comfyui_theme`.
- Don't pass `var(--…)` references as values — resolve to a concrete hex
  or rgba.
- Don't override every token in the inventory. Twenty is plenty.
- If `list_comfyui_tokens` returns a token you don't recognize, leave it
  alone — it's already wired correctly by the design system.

## Worked example

**User:** "Give me a deep ocean theme — dark, cool, with cyan accents."

**Decisions:**

- Mode: dark → override `charcoal-*`, leave `smoke-*` alone.
- Scheme: monochromatic blue-green with cyan accent.
- Charcoal ramp: shift toward a navy undertone (slight desaturation).
- Azure ramp: re-tune toward true cyan, brighter highlights.
- App-mode go: cool teal (reads as "go" without competing with the cyan
  accent); stop: warm coral so it still reads as warning.

**Tool call:**

    write_comfyui_theme(
      name="deep-ocean",
      overrides={
        "color-charcoal-100": "#5a6e80",
        "color-charcoal-200": "#4a5e72",
        "color-charcoal-300": "#3d5163",
        "color-charcoal-400": "#324453",
        "color-charcoal-500": "#293645",
        "color-charcoal-600": "#1f2c39",
        "color-charcoal-700": "#16222e",
        "color-charcoal-800": "#0c1620",
        "color-azure-300": "#7df9ff",
        "color-azure-400": "#00d4ff",
        "color-azure-600": "#00a3cc",
        "app-mode-go-bg": "#00b894",
        "app-mode-go-bg-hover": "#00d2a8",
        "app-mode-go-border": "#007a64",
        "app-mode-stop-bg": "#ff6b6b",
        "app-mode-stop-bg-hover": "#ff8585",
        "app-mode-stop-border": "#cc3333",
      }
    )

Then `apply_comfyui_theme(name="deep-ocean")`, then summarize:

> Applied a deep-ocean dark theme: navy-shifted neutrals, cyan accent
> ramp, teal Run / coral Stop. Vite HMR should refresh the browser. Say
> "warmer", "more saturation", or "more contrast" to iterate.
