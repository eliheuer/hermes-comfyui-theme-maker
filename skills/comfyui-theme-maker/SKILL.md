# ComfyUI Theme Maker

Generate a cohesive ComfyUI frontend theme from a natural-language
description. Output is a CSS custom-property override file written into
the user's local ComfyUI_frontend checkout, where Vite HMR picks it up
live.

## When to use

User says something like "make ComfyUI dark and synthwave", "theme it
like a 90s terminal", "warm neutrals with a gold accent."

## Establishing the frontend path

`write_comfyui_theme`, `apply_comfyui_theme`, `render_theme_swatch`,
and `render_theme_image` all require an explicit `frontend_path`
argument; the tools deliberately do not auto-detect.

On the first theme of a session, check the memory tool for
`comfyui_frontend_path`. If absent, ask the user (e.g. *"Where is your
ComfyUI_frontend checkout?"*), then save their answer to memory under
that key. Pass the value to every tool call needing it.

## Preferred workflow — visual research

1. **`list_comfyui_tokens(layer="all")`** to ground in the real
   override surface. Don't invent token names.

2. **Plan a mood prompt** for the diffusion model. Translate the user's
   request into a concrete anime-styled scene: subjects, lighting,
   color cues. The Anima/Qwen stack is anime / non-photorealistic;
   describe accordingly. Quality boilerplate is added automatically.

3. **`generate_mood_image(prompt=…, size=768)`** — typical latency
   10–25 s on M-series.

4. **`extract_palette_from_image(path=…, n_colors=8)`** — returns
   `[{hex, percent}, …]` sorted by pixel count.

5. **Map the colors onto token ramps:**
   - Sort by perceived lightness. The 4–6 darkest become the
     `charcoal` ramp anchors; `charcoal-800` darkest, `charcoal-100`
     lightest. Interpolate intermediate steps so the spine is monotonic.
   - The 1–2 most saturated colors become **one** accent ramp. Warm →
     `coral-*` or `gold-*`. Cool → `azure-*` or `magenta-*`. Re-tune
     all steps so hover/active stay coherent (lower number = lighter).
   - `app-mode-go-bg` is green with decent contrast against
     `charcoal-800`; `bg-hover` slightly lighter, `border` darker.
     Mirror for `app-mode-stop-*` in red.

6. **`write_comfyui_theme(name=…, overrides=…, frontend_path=…)`**.
   Names omit the leading `--`. Values must be concrete (hex / rgb /
   rgba), not `var()`.

7. **`apply_comfyui_theme(name=…, frontend_path=…)`** — idempotent;
   one theme active at a time. Vite HMR live-reloads.

8. **`render_theme_swatch(name=…, frontend_path=…)`** — include the
   returned `swatch` field **verbatim** in your reply (the ANSI
   escape codes render the colors in the user's terminal).

9. **Briefly summarize**: mode, palette source, accent picks, any
   trade-offs. The user can then iterate.

If the user later asks for a shareable image / social-media version,
call `render_theme_image(name=…, frontend_path=…)` — writes a 1080×1080
PNG. Don't call this in the default loop.

## Iteration without re-generation

When the user says "warmer", "more contrast", "less saturated", etc.,
do **not** call `generate_mood_image` again. Adjust the existing
overrides and re-call `write_comfyui_theme` (overwriting the same
`name`) and `apply_comfyui_theme`.

## Fallback — text-only

If `generate_mood_image` errors, skip steps 3–5 and pick palette
anchors from the description using the heuristics below. Tell the
user visual research was unavailable.

## Token taxonomy

Three layers in ComfyUI_frontend:

- **Palette** (`_palette.css`) — `charcoal-*`, `smoke-*`, `ash-*`,
  `electric-*`, `sapphire-*`. Overriding these cascades through every
  semantic token.
- **Extended palette + layout** (`design-system/style.css`) —
  `coral-*`, `gold-*`, `azure-*`, etc. plus `color-layout-*`.
- **App-mode** (`src/assets/css/style.css`, PR #11317) —
  `app-mode-go-*`, `app-mode-stop-*`. Override directly.

## Cascade rule

Always override at the **palette** layer, never at the semantic layer.
Semantic tokens reference palette via `var()` and split between `:root`
(light) and `.dark-theme` (dark) blocks, so overriding `charcoal-*`
applies in dark mode (invisible in light) and `smoke-*` is the mirror.
The user's existing dark/light toggle keeps working through your theme.

So: dark theme → override `charcoal-*`. Light theme → override
`smoke-*`. Both → override both. Accents and app-mode tokens are
mode-independent.

## Design heuristics

- **Contrast first.** Background-to-foreground luminance ratio should
  exceed 7:1 for body text on neutrals.
- **One accent.** Don't introduce two competing high-saturation hues.
- **Run = green, Stop = red.** Override to other hues only if the user
  explicitly asks; warn that it weakens the safety affordance.

## Minimum viable override set

12–20 overrides is enough:

- All 8 steps of the mode-appropriate neutral ramp (`charcoal-*` for
  dark, `smoke-*` for light).
- One accent ramp, all steps.
- All 6 `app-mode-go-*` / `app-mode-stop-*` tokens.

## Failure modes

- Don't include `--` in token names.
- Don't pass `var(--…)` references as values.
- Don't override every token in the inventory.
- If `list_comfyui_tokens` returns a token you don't recognize, leave
  it alone — the design system already wires it correctly.
