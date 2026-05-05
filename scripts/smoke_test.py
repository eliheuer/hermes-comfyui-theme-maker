#!/usr/bin/env python3
"""End-to-end smoke test for the plugin's tools.

Runs against the local cache (~/.cache/hermes-comfyui-theme-maker/);
exercises the canonical-JSON I/O without requiring a running ComfyUI.
The apply_comfyui_theme step IS skipped unless the env var
HERMES_SMOKE_TEST_LIVE_APPLY=1 is set, since it requires ComfyUI to
be running and would mutate user settings.

Run:
    python3 scripts/smoke_test.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import types
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def _load_plugin_modules():
    pkg_name = "_hermes_comfyui_theme_maker_plugin"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(PLUGIN_ROOT)]
    sys.modules[pkg_name] = pkg
    for sub in ("token_inventory", "schemas", "tools"):
        spec = importlib.util.spec_from_file_location(
            f"{pkg_name}.{sub}", PLUGIN_ROOT / f"{sub}.py"
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f"{pkg_name}.{sub}"] = mod
        spec.loader.exec_module(mod)
    return sys.modules[f"{pkg_name}.tools"]


tools = _load_plugin_modules()


_PASS = 0
_FAIL = 0


def _label(msg):
    print(f"\n[{_PASS + _FAIL + 1:>2}] {msg}")


def _ok(msg):
    global _PASS
    _PASS += 1
    print(f"     pass  {msg}")


def _bad(msg):
    global _FAIL
    _FAIL += 1
    print(f"     FAIL  {msg}")


def _expect_ok(payload, msg):
    if "error" in payload:
        _bad(f"{msg} (got error: {payload['error']})")
        return False
    _ok(msg)
    return True


def _expect_error(payload, msg):
    if "error" not in payload:
        _bad(f"{msg} (expected error, got {payload!r})")
        return False
    _ok(f"{msg} (rejected: {payload['error']})")
    return True


def _T(_tool, **kw):
    handler = getattr(tools, _tool)
    return json.loads(handler(kw))


def _sample_palette(theme_id="smoke-test", **overrides):
    base = {
        "id": theme_id,
        "name": "Smoke Test",
        "light_theme": False,
        "colors": {
            "node_slot": {},
            "litegraph_base": {
                "NODE_TITLE_COLOR": "#bf7c49",
                "NODE_DEFAULT_BGCOLOR": "#2b1e16",
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
                "bar-shadow": "rgba(16, 10, 8, 0.5) 0 0 0.5rem",
            },
        },
    }
    base.update(overrides)
    return base


def main():
    cache = Path(
        os.environ.get(
            "HERMES_COMFYUI_CACHE_DIR",
            "~/.cache/hermes-comfyui-theme-maker",
        )
    ).expanduser()
    smoke_a = cache / "smoke-test.json"
    smoke_b = cache / "smoke-test-2.json"
    smoke_a.unlink(missing_ok=True)
    smoke_b.unlink(missing_ok=True)

    try:
        _label("list_comfyui_tokens(group='all')")
        payload = _T("list_comfyui_tokens", group="all")
        if (
            _expect_ok(payload, f"got {payload.get('total_keys')} total keys")
            and payload.get("total_keys") == 16 + 25 + 26
        ):
            _ok("group counts match canonical schema (16 + 25 + 26)")

        _label("list_comfyui_tokens(group='comfy_base')")
        payload = _T("list_comfyui_tokens", group="comfy_base")
        if (payload.get("comfy_base") and len(payload["comfy_base"]) == 26):
            _ok("26 comfy_base keys (17 required + 9 optional)")
        else:
            _bad(f"unexpected comfy_base count: {payload!r}")

        _label("list_comfyui_tokens(group='bogus')")
        _expect_error(_T("list_comfyui_tokens", group="bogus"),
                      "rejects unknown group")

        _label("write_comfyui_theme — invalid id")
        bad = _sample_palette(theme_id="Bad ID")
        _expect_error(_T("write_comfyui_theme", palette=bad),
                      "rejects non-slug id")

        _label("write_comfyui_theme — missing colors")
        _expect_error(
            _T("write_comfyui_theme",
               palette={"id": "x", "name": "X"}),
            "rejects missing colors",
        )

        _label("write_comfyui_theme — unknown key in comfy_base")
        bad = _sample_palette()
        bad["colors"]["comfy_base"]["bogus-key"] = "#000000"
        _expect_error(
            _T("write_comfyui_theme", palette=bad),
            "rejects unknown comfy_base key",
        )

        _label("write_comfyui_theme — valid")
        payload = _T("write_comfyui_theme", palette=_sample_palette())
        _expect_ok(payload, f"wrote {payload.get('overrides')}")
        if smoke_a.exists():
            written = json.loads(smoke_a.read_text())
            if (
                written.get("id") == "smoke-test"
                and len(written["colors"]["comfy_base"]) >= 17
            ):
                _ok(f"file at {smoke_a} has correct shape")
            else:
                _bad(f"file shape wrong: {written!r}")
        else:
            _bad(f"file missing: {smoke_a}")

        _label("write_comfyui_theme — empty colors groups still valid")
        minimal = {
            "id": "smoke-test-2",
            "name": "Smoke Test 2",
            "colors": {"node_slot": {}, "litegraph_base": {}, "comfy_base": {}},
        }
        _expect_ok(_T("write_comfyui_theme", palette=minimal),
                   "empty palette accepted")

        _label("render_theme_swatch — valid")
        payload = _T("render_theme_swatch", name="smoke-test")
        if (
            payload.get("ok")
            and payload.get("tokens_in_theme")
            and "\033[48;2;" in payload.get("swatch", "")
        ):
            _ok(
                f"rendered swatch ({payload['tokens_in_theme']} tokens, "
                f"{len(payload['swatch'])} bytes ANSI)"
            )
        else:
            _bad(f"unexpected: {payload!r}")

        _label("render_theme_swatch — missing theme")
        _expect_error(_T("render_theme_swatch", name="does-not-exist"),
                      "rejects missing theme")

        _label("render_theme_image — valid")
        out_image = Path("~/Temp/smoke-test-image.png").expanduser()
        out_image.unlink(missing_ok=True)
        payload = _T("render_theme_image", name="smoke-test",
                     output_path=str(out_image))
        if (
            payload.get("ok")
            and payload.get("size") == "1080x1080"
            and out_image.exists()
            and out_image.stat().st_size > 1000
        ):
            _ok(f"wrote {out_image.stat().st_size} bytes")
        else:
            _bad(f"unexpected: {payload!r}")
        out_image.unlink(missing_ok=True)

        _label("render_theme_image — missing theme")
        _expect_error(_T("render_theme_image", name="does-not-exist"),
                      "rejects missing theme")

        if os.environ.get("HERMES_SMOKE_TEST_LIVE_APPLY") == "1":
            _label("apply_comfyui_theme — live (requires ComfyUI running)")
            payload = _T("apply_comfyui_theme", name="smoke-test")
            if payload.get("ok"):
                _ok(f"registered: {payload.get('registered_count')} customs")
            else:
                _bad(f"apply failed: {payload!r}")
        else:
            _label("apply_comfyui_theme — skipped")
            _ok("skipped (set HERMES_SMOKE_TEST_LIVE_APPLY=1 to enable)")

    finally:
        smoke_a.unlink(missing_ok=True)
        smoke_b.unlink(missing_ok=True)

    print(f"\nresults: {_PASS} pass, {_FAIL} fail")
    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
