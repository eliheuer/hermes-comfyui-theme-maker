# ComfyUI_frontend theme system — upstream PR opportunities

Surfaced during the App Mode PR (#11317) migration to the existing
theme system, plus the earlier theme-system research. Each item is a
self-contained PR. They can ship independently and in any order
unless noted.

Repo: `Comfy-Org/ComfyUI_frontend`.

## Strategic context — must read before filing

**The team has already filed the umbrella issue:**
[`#11048`](https://github.com/Comfy-Org/ComfyUI_frontend/issues/11048)
— *"4 layered color systems create fragile overrides"*. Filed by their
internal `audit-code` skill, labels `audit:conflicting`,
`area:vue-migration`. Reference this in every PR description below.

Quote (their words):

> "The color palette service dynamically overrides CSS variables set
> by the design system, which can be fragile. As PrimeVue is
> migrated away, one layer will eventually be removed. **Consider
> having the palette system generate Tailwind-compatible tokens
> directly.**"

**Three implications for our PR strategy:**

1. **Add tokens at the design-system `@theme` layer, not as new
   `comfy_base` palette keys** wherever possible. Adding to comfy_base
   grows the layer that's eventually being collapsed; adding to
   design-system Tailwind tokens aligns with the migration target.
   PRs #1, #2, #3, #4 below all follow this pattern.

2. **PrimeVue (layer 1) is being phased out.** Don't propose anything
   that increases PrimeVue dependency. Don't worry about preserving
   PrimeVue-specific paths.

3. **The hydration FOUC bug is a credible "I understand the system"
   PR.** Customizing palettes hydrate at `GraphCanvas.onMounted`
   (line 566), but `GraphView`'s palette watcher fires earlier with
   `immediate: true` (line 137). For users with a custom palette as
   active, the page paints with default-dark briefly before the
   custom palette is found. Moving the hydration into the bootstrap
   chain fixes it. Filed below as PR #10.

**Related concrete open bug:**
[`#2153`](https://github.com/Comfy-Org/ComfyUI_frontend/issues/2153)
— palette modification distinction (legacy `custom_` migration path).
Lower priority but mention if PR #6 (file-based discovery) is filed,
since that PR touches the same custom-palette codepath.

---

## 1. Symmetric hover/border tokens for action-button colors

**Problem.** Design-system has `--destructive-background-hover` but no
`--success-background-hover`, no `--success-border`, no
`--destructive-border`. The App Mode Run / Stop buttons originally
introduced their own `--app-mode-go-bg-hover` etc. because the palette
didn't supply equivalents. Migrating away from the local tokens forced
a workaround (`filter: brightness(1.1)`) that works but isn't
authorable per palette — palette designers can't tune the hover state.

**Solution.** Add the missing symmetric tokens to the design-system
`@theme` block and reference them from `:root` and `.dark-theme`:

```css
/* design-system/src/css/style.css @theme inline */
--color-success-background-hover: var(--success-background-hover);
--color-success-border:           var(--success-border);
--color-destructive-border:       var(--destructive-border);

/* :root (light mode) */
--success-background-hover: var(--color-jade-400);
--success-border:           var(--color-jade-600);
--destructive-border:       var(--color-coral-700);

/* .dark-theme */
--success-background-hover: var(--color-jade-400);
--success-border:           var(--color-jade-600);
--destructive-border:       var(--color-coral-700);
```

**Files.** `packages/design-system/src/css/style.css` (declarations
only).

**Backwards compatibility.** Pure addition; no existing usage breaks.

**Notes.** The "buttons don't need borders, just bg" convention is
also reasonable — modern flat design supports both. If the team
prefers borderless action buttons, omit the border tokens and codify
"action buttons are solid bg with `border-0` and rely on hover
brightness/transform" as a documented convention. Either choice
unblocks the App Mode migration.

---

## 2. Focus-state border color token

**Problem.** No dedicated `--border-color-focus` (or equivalent) in
the palette schema. App Mode currently uses `var(--fg-color)` for the
input focus border — full contrast, often too aggressive (white on
near-white widget surface in some palettes; black on near-black in
others).

**Solution.** Add a `border-color-focus` (or `border-focus`) key to
the optional `comfy_base` group in the palette schema. Each built-in
palette gets a sensible default. The fallback mechanism
(`var(--palette-${key})`) provides a design-system default when a
palette doesn't override.

```ts
// src/schemas/colorPaletteSchema.ts comfyBaseSchema
['border-color-focus']: z.string().optional(),
```

**Files.**
- `src/schemas/colorPaletteSchema.ts` — schema addition.
- `src/services/colorPaletteService.ts` — already iterates the
  comfy_base keys; no logic change needed if the key is in the
  optional fallback table.
- `src/assets/palettes/{dark,light,arc,nord,solarized,github}.json`
  — add a value or rely on fallback.
- `packages/design-system/src/css/style.css` — `--palette-border-color-focus`
  default.

**Backwards compatibility.** Optional key; existing palettes still
validate. Falls back to `var(--palette-border-color-focus)` design-
system default when missing.

---

## 3. Text-selection background token

**Problem.** No palette-level `::selection` color. Browser default
reads as a system-blue artifact on dark surfaces. App Mode originally
introduced `--app-mode-widget-selection-bg` for this; we dropped that
override entirely as part of the theme-system migration, and selection
on dark backgrounds now flashes blue.

**Solution.** Add `selection-background` and (optionally)
`selection-foreground` to optional `comfy_base`. Apply via a global
`::selection` rule.

```ts
// schema
['selection-background']: z.string().optional(),
['selection-foreground']: z.string().optional(),
```

```css
/* applied globally in design-system */
::selection {
  background-color: var(--selection-background);
  color: var(--selection-foreground);
}
```

**Files.** Same set as PR #2.

**Backwards compatibility.** Optional + fallback; pure addition.

---

## 4. Subtle chrome-border variant

**Problem.** `--border-color` is tuned for inputs and dividers — it's
strong on every theme. Chrome surfaces (floating panels, headers, the
Builder menu) want a *subtler* border. The App Mode PR's previous
`rgb(255 255 255 / 0.08)` was that subtler variant; migrating to
`--border-color` makes the chrome read heavier than designed.

**Solution.** Add `border-color-subtle` to optional `comfy_base`.
~30% opacity of `--border-color` is a sensible default if the palette
doesn't override.

**Files.** Same as PR #2.

**Notes.** Could alternatively introduce `--chrome-border` (named
after its semantic use) rather than a generic "subtle" variant; the
team's convention should drive the name.

---

## 5. App-mode palette schema extension (action-button colors)

**Problem.** Even with PRs #1–#4 above, action-button-specific
semantics (Run = green, Stop = red, with hover and border states)
aren't first-class palette concerns. Palette authors can theme
"success" and "destructive" generally — but App Mode users may want
distinct Run/Stop tones from the general success/destructive
spectrum.

**Solution (option A — minimal):** *no schema change.* App Mode
treats `--success-background` and `--destructive-background` as the
authoritative source. Palette authors influence Run/Stop via those
existing tokens.

**Solution (option B — explicit):** add an optional `app_mode` color
group to the palette schema, alongside `node_slot` / `litegraph_base`
/ `comfy_base`. Currently empty conceptually; reserved for future
App-Mode-specific tokens.

```ts
const colorsSchema = z.object({
  node_slot: nodeSlotSchema,
  litegraph_base: litegraphBaseSchema,
  comfy_base: comfyBaseSchema,
  app_mode: appModeSchema.optional()  // NEW, optional
})
```

Pick option A unless someone files a concrete need for App-Mode-
specific Run/Stop tones distinct from general success/destructive.
Option A is friction-free and doesn't fragment the palette model.

---

## 6. File-based palette discovery

**Problem.** A user / generator that drops a `.json` palette into
`<frontend>/src/assets/palettes/` won't see it in the theme menu
unless they also call `addCustomColorPalette(...)` or import via the
Settings UI. Built-in palettes are discovered (hardcoded in
`coreColorPalettes.ts`); user palettes aren't symmetric.

**Solution.** Add a userland palette directory (e.g.
`<frontend>/user/palettes/` or `<ComfyUI install>/user/palettes/`)
that gets scanned at app boot, validated against the schema, and
merged into `customPalettes` in the store. A "Reload palettes" button
in Settings → Appearance triggers a re-scan without restart.

**Files.**
- `src/services/colorPaletteService.ts` — add `discoverFilePalettes()`
  helper, called at bootstrap.
- `src/stores/workspace/colorPaletteStore.ts` — accept the discovered
  set the same way custom palettes are added.
- `src/components/dialog/content/setting/ColorPaletteImport.vue` (or
  wherever the Appearance UI lives) — add the reload button.

**Backwards compatibility.** Pure addition; existing import flow
unchanged.

**Why this matters for tooling.** Generator tools (like
hermes-comfyui-theme-maker) can write a JSON to the discovery dir and
have it appear in the menu without dynamic JS calls. Dropfile
distribution becomes a real channel.

---

## 7. Reload-palettes button in Appearance settings

**Problem.** Importing a palette today requires the Settings →
Appearance → Color Palette → Import flow per file. There's no way to
trigger a re-scan after dropping multiple palettes into a directory or
after editing one.

**Solution.** Trivial UI addition that calls the discovery routine
from PR #6.

**Files.** Same as PR #6's UI file.

**Notes.** Pairs naturally with PR #6 — could ship as one PR.

---

## 8. Document the palette schema as stable public API

**Problem.** [`docs.comfy.org/interface/appearance`](https://docs.comfy.org/interface/appearance)
says the palette schema "may change with frontend updates," which
discourages tooling and community port effort. The schema *has* been
stable for some time and the additions in PRs #2–#5 above are
backwards-compatible. Tool authors need a stable contract.

**Solution.**
- Pin a schema version (the community already uses `version: 102` —
  formalize it).
- Publish a CHANGELOG entry whenever the schema changes.
- Update the docs to clarify that the schema is stable and any future
  changes are additive (optional fields) unless versioned.
- Optionally: emit the Zod schema as JSON Schema and publish at a
  stable URL so external tools can validate without depending on
  ComfyUI_frontend's package.

**Files.** Mostly docs; no code change required for the contract
itself, but adding a `version` constant in
`src/constants/coreColorPalettes.ts` would make it canonical.

---

## 9. Fix `user.css` overwrite-on-update bug

**Problem.** `ComfyUI/user/<username>/user.css` (the official escape
hatch for arbitrary CSS overrides) gets wiped on update.

- [`comfyanonymous/ComfyUI#1999`](https://github.com/comfyanonymous/ComfyUI/issues/1999)
- [`comfyanonymous/ComfyUI#6544`](https://github.com/comfyanonymous/ComfyUI/issues/6544)

Themes that can't be expressed via the palette schema (typography,
spacing, advanced layout) lose all changes after every update.

**Solution.** Likely upstream of the frontend (in the
comfy-installer / workflow-templates / ComfyUI backend), but the
frontend can at minimum *load* user.css without writing to it during
normal operation. Worth confirming whether the overwrite is
frontend-side or installer-side.

**Files.** TBD — depends on which side is actually overwriting.

**Priority.** Lower than the schema improvements but high-impact for
ricing / power-user workflows.

---

## 10. Fix the custom-palette hydration FOUC

**Problem.** A user whose active palette is a custom one sees the
default-dark palette paint briefly before their custom palette is
applied, on every reload. Caused by an ordering issue:

1. `GraphView.vue:137-154` watches `colorPaletteStore.completedActivePalette`
   with `immediate: true`. Fires at component-mount time.
2. At that moment, `colorPaletteStore.customPalettes` is still `{}`.
3. The user's active id (a custom palette) doesn't resolve in
   `palettesLookup`. Falls back to default-dark.
4. `.dark-theme` class is set; first paint happens.
5. Later, `GraphCanvas.vue:566-568`'s `onMounted` runs:
   `colorPaletteStore.customPalettes = settingStore.get('Comfy.CustomColorPalettes')`.
6. `palettesLookup` recomputes. Watcher refires. Correct palette
   applied. Visible flash.

**Solution.** Move the customs hydration earlier — into the same
bootstrap chain that loads settings, before any component mounts.
Either:

- Add a step at the end of `bootstrapStore.loadAuthenticatedStores()`
  that does the assignment.
- Or expose a `colorPaletteStore.hydrateFromSettings()` helper and
  call it from bootstrapStore.

**Files.**
- `src/stores/bootstrapStore.ts` (or wherever `loadAuthenticatedStores`
  lives).
- `src/stores/workspace/colorPaletteStore.ts` (add the helper if used).
- Remove the assignment from `src/components/graph/GraphCanvas.vue:566-568`.

**Tests.** Add a browser test that:
- Imports a custom palette, sets it active, persists.
- Reloads.
- Asserts no flash of default-dark before custom is applied.

**Notes.** This is the highest-credibility PR to file first — it's a
real concrete bug, easy to reproduce, that any reviewer can verify in
30 seconds. It demonstrates "I read the bootstrap chain carefully."
Reference #11048 as the umbrella context.

---

## Sequencing recommendation

1. **First**: **PR #10** (FOUC fix) — concrete bug, high reviewer
   credibility, demonstrates careful reading of the bootstrap chain.
   Reference #11048 as umbrella; reference #2153 as adjacent
   concrete bug.

2. **Second**: PRs #1–#4 (token additions) ship together as one
   "design-system token expansion" PR. Pure additions at the
   `@theme` layer (aligns with the Tailwind-direction signaled in
   #11048). All the App Mode follow-ups (and other UI work)
   immediately benefit.

3. **Third**: PR #6 + #7 together ("file-based palette discovery
   plus reload button") — one user-visible feature.

4. **Fourth**: PR #8 ("schema stability docs") — small, mostly
   documentation; can ship anytime.

5. **Independent**: PR #9 (user.css fix) — investigate and fix when
   bandwidth allows.

6. **Open question**: PR #5 (app-mode group) — wait for concrete
   demand before adding schema complexity.

After PRs #1–#4 land, the App Mode PR (#11317) follow-up is to swap
its `filter: brightness(1.1)` workaround back to
`var(--success-background-hover)` and similar — three or four
one-line changes.

---

## Appendix: where these came from

- App Mode PR migration in `~/Work/comfy/repos/ComfyUI_frontend` on
  branch `app-mode-semi-customizable-layout`. Dropped 14
  `--app-mode-*` tokens; mapped each to existing palette tokens or
  behavior-based effects. The "no equivalent" rows in that mapping
  table are the schema gaps fixed by PRs #1–#4.

- Theme-system research in
  [`docs/comfyui-theme-system.md`](./comfyui-theme-system.md) — full
  schema reference, bootstrap timeline, light/dark mechanics,
  PrimeVue integration, test coverage, distribution channels,
  ricing-community state.

- Source files (all in ComfyUI_frontend):
  - `src/schemas/colorPaletteSchema.ts`
  - `src/constants/coreColorPalettes.ts`
  - `src/services/colorPaletteService.ts`
  - `src/stores/workspace/colorPaletteStore.ts`
  - `src/views/GraphView.vue:137-154` (light/dark watcher)
  - `src/components/graph/GraphCanvas.vue:566-568` (custom hydration)
  - `src/main.ts` (PrimeVue setup, dark-mode selector)
  - `src/assets/palettes/*.json`
  - `packages/design-system/src/css/style.css`
