# hermes-comfyui-theme-maker

Generate cohesive [ComfyUI frontend](https://github.com/Comfy-Org/ComfyUI_frontend)
themes from natural-language descriptions, fully locally on Apple Silicon, via
a [Hermes Agent](https://hermes-agent.nousresearch.com/) skill plus tools.

Built for the Hermes Agent Creative Hackathon.

## What it does

- A **skill** (`comfyui-theme`) that loads the canonical ComfyUI token
  taxonomy and design heuristics into Hermes' context.
- Three **tools** the agent calls:
  - `list_comfyui_tokens` — return every overridable CSS custom property.
  - `write_comfyui_theme` — write a theme file to your ComfyUI_frontend
    checkout.
  - `apply_comfyui_theme` — activate the theme via a single `@import`,
    picked up by Vite HMR.
- Targets the three-layer token surface: **palette** (foundational color
  ramps), **semantic** (cascades automatically), and the new **app-mode**
  tokens introduced by ComfyUI_frontend PR #11317
  (`app-mode-semi-customizable-layout`).

## Stack — fully local on Mac M-series

- **llama.cpp** (Metal) serving Nous Research's official
  [Hermes-4.3-36B-GGUF](https://huggingface.co/NousResearch/Hermes-4.3-36B-GGUF).
- **hermes-agent** CLI driving the conversation, pointed at the local
  llama-server endpoint.
- This plugin packaged as a Hermes skill + toolset.
- Your existing **ComfyUI_frontend** Vite dev server for live preview.

## Setup

### 1. Install llama.cpp and the Hermes model

```bash
brew install llama.cpp

# Q4_K_M (~22 GB). Comfortable on 48 GB + ComfyUI running.
huggingface-cli download NousResearch/Hermes-4.3-36B-GGUF \
    "Hermes-4.3-36B-Q4_K_M.gguf" \
    --local-dir ~/models/hermes-4.3-36b
```

Smaller fallback if memory is tight: download `Hermes-4-14B-GGUF` at
`Q5_K_M` (~10 GB) instead.

### 2. Start the inference server

```bash
llama-server \
    --model ~/models/hermes-4.3-36b/Hermes-4.3-36B-Q4_K_M.gguf \
    --ctx-size 65536 \
    --host 127.0.0.1 \
    --port 8080
```

This exposes an OpenAI-compatible endpoint at `http://127.0.0.1:8080`.

### 3. Install hermes-agent

```bash
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
source ~/.zshrc  # or ~/.bashrc
```

Point it at the local endpoint:

```bash
hermes model add local --base-url http://127.0.0.1:8080/v1 \
    --api-key sk-no-key --model hermes-4.3-36b
hermes model use local
```

### 4. Install this plugin

```bash
git clone https://github.com/eliheuer/hermes-comfyui-theme-maker.git \
    ~/GH/repos/hermes-comfyui-theme-maker

# Hermes plugin dirs must be valid Python identifiers — symlink with underscores.
ln -s ~/GH/repos/hermes-comfyui-theme-maker \
      ~/.hermes/plugins/hermes_comfyui_theme_maker
```

### 5. Point the plugin at your ComfyUI_frontend checkout

The default is `~/Work/comfy/repos/ComfyUI_frontend`. Override with:

```bash
export HERMES_COMFYUI_FRONTEND_PATH=/path/to/your/ComfyUI_frontend
```

### 6. Start ComfyUI_frontend

In a separate terminal:

```bash
cd /path/to/ComfyUI_frontend
pnpm dev
```

## Usage

```bash
hermes
```

Then in the chat:

```
> Use the comfyui-theme skill to make a synthwave terminal theme — dark,
  magenta and cyan accents, deep purple background.
```

Hermes will:

1. Call `list_comfyui_tokens` to ground itself in the real token surface.
2. Reason about palette and pick concrete hex values.
3. Call `write_comfyui_theme(name="synthwave-terminal", overrides={…})`.
4. Call `apply_comfyui_theme(name="synthwave-terminal")`.

Vite HMR live-reloads the browser. Iterate by saying "make it warmer" or
"less saturated" — Hermes will rewrite and re-apply.

## How it works

ComfyUI_frontend exposes a clean three-layer CSS custom-property system:

1. **Palette** (`_palette.css`) — raw color ramps (`charcoal-*`,
   `smoke-*`, etc.).
2. **Semantic** (`design-system/style.css`) — semantic tokens that
   reference the palette (`base-foreground`, `secondary-background`, …).
3. **App-mode** (`src/assets/css/style.css`) — local tokens for the new
   App Mode redesign (`--app-mode-go-*`, `--app-mode-widget-*`).

This plugin emits a single `theme.css` file that overrides tokens at the
palette and app-mode layers. The semantic layer cascades automatically.
`apply` injects one `@import` line into `style.css` between sentinel
comments — idempotent, removable, single source of truth.

> **Heads up:** `apply_comfyui_theme` modifies your tracked
> `src/assets/css/style.css`. To revert: `git restore
> src/assets/css/style.css`.

## Tested against

- ComfyUI_frontend `main`
- ComfyUI_frontend PR #11317 branch `app-mode-semi-customizable-layout`
  in graph mode, app mode, and builder mode

## License

GPL-3.0-or-later. See [LICENSE](./LICENSE).
