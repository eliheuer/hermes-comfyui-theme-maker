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

## Failure modes to avoid

- Don't include `--` in token names passed to `write_comfyui_theme`.
- Don't pass `var(--…)` references as values — resolve to a concrete hex
  or rgba.
- Don't override every token in the inventory. Twenty is plenty.
- If `list_comfyui_tokens` returns a token you don't recognize, leave it
  alone — it's already wired correctly by the design system.

## Worked example

**User:** "Give me a deep ocean theme — dark, cool, with cyan accents."

**Plan:**

- Mode: dark.
- Scheme: monochromatic blue-green with cyan accent.
- Charcoal ramp: shift toward a slight blue undertone (desaturated navy).
- Azure ramp: re-tune toward true cyan.
- App-mode go: cool teal; stop: muted coral so it still reads as warning.

Then call `write_comfyui_theme(name="deep-ocean", overrides={…})` followed
by `apply_comfyui_theme(name="deep-ocean")`.
