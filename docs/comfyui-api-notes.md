# ComfyUI HTTP API notes

Everything we need to know to drive the local ComfyUI instance from
Python tools. Verified against ComfyUI v0.19.3 running at
`http://127.0.0.1:8188` on the user's M4.

## Endpoints we actually use

| Method + path | Purpose |
|---|---|
| `GET /system_stats` | Health check — no body, returns OS/RAM/devices |
| `POST /prompt` | Submit a workflow for execution |
| `GET /queue` | Inspect running + pending jobs |
| `GET /history/<prompt_id>` | Get execution result + output references |
| `GET /view` | Download a generated file |

There's also `WS /ws` for real-time progress events (`executing`,
`progress`, `executed`). We start with simple polling against
`/history` for layer 2 — websocket only if polling latency is bad.

## Prompt format vs. workflow format

ComfyUI has two JSON shapes for the same graph:

- **Workflow format** — what the UI saves in
  `~/Work/comfy/repos/ComfyUI/user/default/workflows/*.json`. Has
  `nodes` (with `pos`, `widgets_values`, `flags`), `links` (positional
  edge tuples), `groups`, viewport state. *This is for the UI.*
- **Prompt format** — what `/prompt` accepts. A flat dict keyed by node
  id; each node is `{class_type, inputs}`. Inputs are either literal
  values or `[upstream_node_id, output_index]` pairs. *This is for the
  API.*

The two are semantically equivalent but structurally different. The UI
converts workflow → prompt internally before submitting. We have two
options for our `workflows/anima-turbo.json`:

1. Save in **prompt format** directly, ready to POST as-is. Cleaner —
   no conversion step at runtime. Drawback: harder to author in the UI.
2. Save in **workflow format**, port to prompt format on first run. Lets
   us reuse the user's saved workflow file directly.

Pick option 1 — author the prompt-format JSON once by hand from the
saved workflow file as a one-off, store it in `workflows/`, parameterize
the prompt text and image size with placeholders.

## Submitting a workflow

Minimum POST body:

```json
{
  "prompt": { /* prompt-format graph */ },
  "client_id": "hermes-comfyui-theme-maker"
}
```

Response shape on success:

```json
{
  "prompt_id": "9f3b…",
  "number": 12,
  "node_errors": {}
}
```

`node_errors` is non-empty if validation fails (missing model file,
unknown node type, type mismatch). Treat any non-empty `node_errors`
as a failure; surface the contents in the tool's error message.

## Polling for completion

```
GET /history/<prompt_id>
```

When the prompt is queued or running the response is `{}` or omits the
prompt id. When complete:

```json
{
  "<prompt_id>": {
    "prompt": [/* echo of submission */],
    "outputs": {
      "<output_node_id>": {
        "images": [
          {"filename": "ComfyUI_00012_.png", "subfolder": "", "type": "output"}
        ]
      }
    },
    "status": {"status_str": "success", "completed": true, ...}
  }
}
```

Poll cadence: 500 ms is fine, Anima turbo is ~5–15 s on M4. Hard
timeout at ~60 s. The output node id depends on the workflow — the
final `SaveImage` (or equivalent) node's id. Hard-code it in the
prompt-format JSON we ship.

## Fetching the output image

```
GET /view?filename=ComfyUI_00012_.png&type=output
```

`type` is one of `output`, `input`, `temp`. The response is the raw
image bytes with the correct content type. Save to a known location
(e.g. `~/.cache/hermes-comfyui-theme-maker/<prompt_id>.png`) so
`extract_palette_from_image` can read it back.

## Workflow template parameterization

The Anima turbo workflow has a small set of inputs we want to expose:

| Variable | Where in the workflow | Default |
|---|---|---|
| Positive prompt text | `CLIPTextEncode` node feeding the sampler positive | (from tool arg) |
| Negative prompt text | `CLIPTextEncode` node feeding the sampler negative | "low quality, watermark, text" |
| Width / height | `EmptyQwenImageLayeredLatentImage` (or equivalent) | 768 × 768 |
| Seed | `KSampler` seed input | random unless overridden |
| Steps | `KSampler` steps input | small (Anima turbo is fast) |

At tool runtime we deep-copy the template, splice in the variables,
POST it. No string templating — manipulate as Python dict.

## Output location on disk

ComfyUI writes generated images to its own output dir, default
`~/Work/comfy/repos/ComfyUI/output/`. Our tool does **not** need to
reach into that dir: we always go through `/view` over HTTP, save to
our own cache. That keeps the tool location-agnostic and avoids
coupling to ComfyUI's filesystem layout.

## Error surfaces worth catching

| Error | Likely cause | Tool response |
|---|---|---|
| Connection refused on `:8188` | ComfyUI not running | `{error: "ComfyUI not reachable at <url>"}` |
| 400 from `/prompt` with `node_errors` | wrong node type / missing model | echo `node_errors` content |
| Polling timeout | OOM, hang, large image | `{error: "generation timeout after 60 s"}` |
| `/view` returns 404 | output ref stale or wrong subfolder | `{error: "output file missing — check ComfyUI logs"}` |
| Workflow json malformed | bug in parameterization | catch, return `{error: "internal: …"}` |

All of these are recoverable from the agent's perspective: it falls
back to text-only theme generation per the skill instructions.

## References for future reading

- ComfyUI HTTP API source — `~/Work/comfy/repos/ComfyUI/server.py`
  (route definitions live near `add_routes`).
- Workflow → prompt conversion happens in the frontend; for our
  purposes hand-converting once is simpler than reading that code.
- `GET /object_info` returns the full inventory of node types and
  their inputs/outputs — useful when authoring the prompt-format JSON.
