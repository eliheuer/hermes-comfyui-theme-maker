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

The **preferred** workflow uses ComfyUI to generate a small reference
image first, then extracts a real palette from it to anchor the theme.
A **fallback** workflow skips the image step and reasons from the
description alone — use it when ComfyUI is unreachable, the user
declines visual research, or this is a refinement turn (see "Iteration"
below).

### Establishing the ComfyUI_frontend path (do this once)

`write_comfyui_theme` and `apply_comfyui_theme` both require an explicit
`frontend_path` argument — the absolute path to the user's
ComfyUI_frontend checkout. The tools deliberately do not auto-detect.

Before the first theme of any session:

1. Check the memory tool for a key like `comfyui_frontend_path`. If it
   exists, use that value and skip ahead to the visual-research loop.
2. If not, ask the user explicitly: *"Where is your ComfyUI_frontend
   checkout? (e.g. `~/code/ComfyUI_frontend`)"*. Use the clarify tool
   if available, or ask in chat.
3. Once they answer, save it to memory under `comfyui_frontend_path`
   so future sessions don't have to ask again.
4. Pass that exact value to every `write_comfyui_theme` and
   `apply_comfyui_theme` call.

### Preferred workflow — visual-research loop

1. **Call `list_comfyui_tokens(layer="all")`** to ground yourself in the
   real override surface. Do not invent token names.
2. **Plan a mood prompt for the image generator.** Translate the user's
   request into a concrete anime-styled scene description: subjects,
   lighting, color cues, atmosphere. The Anima/Qwen stack is anime /
   non-photorealistic, so describe accordingly. Quality boilerplate
   ("masterpiece, best quality, ...") is added automatically — don't
   include it yourself.
3. **Call `generate_mood_image(prompt=…, size=768)`** to get a reference
   PNG. Typical latency: 10–25 s on M-series.
4. **Call `extract_palette_from_image(path=…, n_colors=8)`** to get the
   dominant colors as `[{hex, percent}, …]` sorted by pixel count.
5. **Map extracted colors onto token ramps.**
   - Sort the returned colors by perceived lightness (eyeball — darker
     hex first). The 4–6 darkest become the `charcoal` ramp anchors:
     `charcoal-800` is the darkest, `charcoal-100` the lightest. Pick
     intermediate ramp steps by interpolating lightness between anchors
     so the spine remains monotonic.
   - The 1–2 most saturated colors become accent ramp anchors. A warm
     accent → `coral-*` or `gold-*`. A cool accent → `azure-*` or
     `magenta-*`. Re-tune all steps of the chosen ramp so hover/active
     stay coherent (lower-numbered = lighter, higher = darker).
   - Pick `app-mode-go-bg` as a green that has decent contrast with
     `charcoal-800`; `bg-hover` slightly lighter, `border` darker.
     Mirror for `app-mode-stop-*` in red.
6. **Call `write_comfyui_theme(name=…, overrides=…, frontend_path=…)`.**
   Names omit the leading `--`. Values must be concrete (hex, rgb, rgba),
   not `var()`. `frontend_path` is the user's checkout you established
   above.
7. **Call `apply_comfyui_theme(name=…, frontend_path=…)`.** Idempotent;
   one theme at a time. Vite HMR live-reloads.
8. **Call `render_theme_swatch(name=…, frontend_path=…)`** to render
   the theme as ANSI-colored blocks grouped by category. Include the
   returned `swatch` field **verbatim** in your reply (don't re-format
   it — the escape codes render the colors in the user's terminal).
9. **Briefly summarize.** One short paragraph: mode, where the palette
   came from (the generated reference), accent picks, any notable
   trade-offs. The user can then iterate ("warmer", "less saturated",
   "more contrast").

If the user later asks for a **shareable image / social-media version /
infographic** of the theme, call `render_theme_image(name=…,
frontend_path=…)`. It writes a 1080×1080 PNG to
`~/.cache/hermes-comfyui-theme-maker/<name>.png` (or a path the user
specified) and returns the file path. Don't call this as part of the
default loop — only on explicit request.

### Fallback workflow — text-only

If `generate_mood_image` returns an `error` field, do **not** retry
endlessly. Skip steps 3–5 of the preferred workflow and pick palette
anchors from the description using your own design judgment plus the
heuristics below. Mention to the user that visual research was
unavailable so the result is description-only.

### Iteration — refining without re-generation

When the user says "warmer", "more contrast", "less saturated", etc.
about an already-applied theme, do **not** call `generate_mood_image`
again. Read the existing overrides, adjust the relevant hex values, and
call `write_comfyui_theme` (overwriting the same `name`) and
`apply_comfyui_theme`. Vite HMR re-loads with the tweak.

## Mapping extracted palettes onto ramps

When `extract_palette_from_image` returns 8 colors, you typically have:

- 3–5 dark neutrals → fill the `charcoal` ramp (or `smoke` for light
  themes). If fewer than 8 ramp steps have direct anchors, interpolate
  the gaps so lightness steps evenly.
- 1–2 warm or cool saturated colors → one accent ramp. Don't try to
  cover two accent ramps from a single image; pick one.
- 1–2 mid-tones → mostly redundant for ramp anchors. Useful for
  `node-component-*` semantic tokens if they look notably different.

Heuristic for assigning the darkest extracted color: it almost always
goes on `charcoal-800` (primary dark background). The lightest extracted
color often becomes `charcoal-100` (high-contrast text on dark).

If the extracted palette has *no* clear accent (everything is neutral),
keep the existing accent ramps at default — a desaturated theme reads
as professional, while jamming a forced accent in reads as awkward.

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

## Worked example — preferred workflow

**User:** *"make me a campfire theme"*

**Step 1 — `list_comfyui_tokens(layer="all")`.** Confirm token surface
(67 tokens, 4 layers).

**Step 2 — plan the mood prompt.** Campfire vibe is warm, dark, with
ember oranges and dim ambient. An anime-styled prompt that captures it:

> "a quiet campfire in autumn forest at dusk, warm orange glow on
> burnt logs, soft amber light through leaves, deep ember reds,
> atmospheric fog"

**Step 3 — `generate_mood_image(prompt=…, size=768)`.** Returns
`{ok: true, path: "~/.cache/.../<id>.png", elapsed_seconds: 21.3, ...}`.

**Step 4 — `extract_palette_from_image(path=…, n_colors=8)`.** Returns
something like:

    #181b1e   15.9%   forest dark   (charcoal-800 anchor)
    #635450   13.9%   warm ash gray (charcoal-300 / mid)
    #4e2514   13.7%   charred wood  (charcoal-700 / coral-700)
    #433f3f   12.6%   warm dark gray
    #292323   12.5%   ember soot    (charcoal-700)
    #793d26   11.8%   copper sienna (coral-500 anchor)
    #bf7c49   10.7%   fire-glow amber (gold-400 anchor)
    #0f0f10    8.9%   near-black    (charcoal-800 darker)

**Step 5 — map onto ramps.** Charcoal ramp from the warm dark anchors
(monotonic darkening), interpolating gaps. Coral ramp from the copper
sienna with brighter/darker steps derived. Gold ramp from the amber.
App-mode Run / Stop sit at warm green / warm red contrasting against
the dark background.

**Steps 6 and 7 — write and apply** (assuming `frontend_path` was
established earlier as e.g. `/Users/alice/code/ComfyUI_frontend`):

    write_comfyui_theme(
      name="campfire-mood",
      frontend_path="/Users/alice/code/ComfyUI_frontend",
      overrides={
        "color-charcoal-100": "#8a7060",
        "color-charcoal-200": "#6f594a",
        "color-charcoal-300": "#5a473b",
        "color-charcoal-400": "#483830",
        "color-charcoal-500": "#3a2d27",
        "color-charcoal-600": "#2e231e",
        "color-charcoal-700": "#221915",
        "color-charcoal-800": "#15100c",
        "color-coral-500": "#bf7c49",
        "color-coral-600": "#a05a2c",
        "color-coral-700": "#793d26",
        "color-gold-400": "#f5c267",
        "color-gold-500": "#e8a942",
        "color-gold-600": "#c8851f",
        "app-mode-go-bg": "#5a8a35",
        "app-mode-go-bg-hover": "#6da342",
        "app-mode-go-border": "#3d6b22",
        "app-mode-stop-bg": "#c8421f",
        "app-mode-stop-bg-hover": "#e0593a",
        "app-mode-stop-border": "#8a2c12",
      }
    )

Then `apply_comfyui_theme(name="campfire-mood", frontend_path=…)` and
summarize:

> Generated a campfire reference (autumn forest, ember light) and
> mapped its palette onto the theme: warm dark neutrals from the
> forest tones, coral and gold ramps from the ember and amber
> highlights, forest-green Run / warm-red Stop. Browser should
> refresh. Say "warmer", "more saturation", or "more contrast" to
> iterate without re-generating the reference.
