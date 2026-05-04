#!/usr/bin/env python3
"""End-to-end smoke test for the plugin's tools.

Saves and restores style.css around the run; safe to abort.

Run:
    HERMES_COMFYUI_FRONTEND_PATH=/path/to/ComfyUI_frontend \\
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


def main():
    raw = os.environ.get("HERMES_COMFYUI_FRONTEND_PATH")
    if not raw:
        print("abort: set HERMES_COMFYUI_FRONTEND_PATH to your ComfyUI_frontend root")
        return 2
    frontend = Path(raw).expanduser().resolve()
    fp = str(frontend)
    style = frontend / "src" / "assets" / "css" / "style.css"
    themes_dir = frontend / "src" / "assets" / "css" / "themes"
    smoke_a = themes_dir / "smoke-test.css"
    smoke_b = themes_dir / "smoke-test-2.css"

    print(f"target frontend: {frontend}")
    if not style.exists():
        print(f"abort: {style} not found")
        return 2

    style_before = style.read_text()
    if "hermes-comfyui-theme-maker:active" in style_before:
        print("abort: style.css already contains a hermes-comfyui-theme-maker block;")
        print("       run `git restore src/assets/css/style.css` and retry.")
        return 2

    print(f"style.css size before: {len(style_before)} bytes")

    # Compact wrappers — every call site reads as one expression.
    def W(**kw):
        return json.loads(tools.write_theme({"frontend_path": fp, **kw}))

    def A(name):
        return json.loads(tools.apply_theme({"name": name, "frontend_path": fp}))

    def S(name):
        return json.loads(
            tools.render_theme_swatch({"name": name, "frontend_path": fp})
        )

    def I(name, **kw):
        return json.loads(
            tools.render_theme_image({"name": name, "frontend_path": fp, **kw})
        )

    def L(layer="all"):
        return json.loads(tools.list_tokens({"layer": layer}))

    try:
        _label("list_tokens(layer='all')")
        payload = L()
        if _expect_ok(payload, f"got {payload.get('count')} tokens"):
            if payload["count"] != 67:
                _bad(f"expected 67 tokens, got {payload['count']}")
            else:
                _ok("count matches inventory (67)")

        _label("list_tokens(layer='app_mode')")
        payload = L("app_mode")
        if payload.get("count") == 6:
            _ok("6 app_mode tokens")
        else:
            _bad(f"expected 6, got {payload.get('count')}")

        _label("list_tokens(layer='bogus')")
        _expect_error(L("bogus"), "rejects unknown layer")

        _label("write_theme(missing frontend_path)")
        payload = json.loads(
            tools.write_theme(
                {"name": "smoke-test", "overrides": {"color-charcoal-800": "#000000"}}
            )
        )
        _expect_error(payload, "rejects missing frontend_path")

        _label("write_theme(bad frontend_path)")
        payload = json.loads(
            tools.write_theme({
                "name": "smoke-test",
                "overrides": {"color-charcoal-800": "#000000"},
                "frontend_path": "/no/such/place",
            })
        )
        _expect_error(payload, "rejects nonexistent frontend_path")

        _label("write_theme(invalid slug)")
        _expect_error(
            W(name="Bad Slug", overrides={"color-charcoal-800": "#000000"}),
            "rejects slug with spaces and capitals",
        )

        _label("write_theme(empty overrides)")
        _expect_error(
            W(name="smoke-test", overrides={}),
            "rejects empty overrides",
        )

        _label("write_theme(unknown token)")
        payload = W(name="smoke-test", overrides={"color-bogus-999": "#000000"})
        if "error" in payload and "color-bogus-999" in str(payload):
            _ok(f"rejects unknown token (unknown={payload.get('unknown')})")
        else:
            _bad(f"expected unknown-token error, got {payload!r}")

        _label("write_theme(valid)")
        overrides = {
            "color-charcoal-800": "#0a0a0f",
            "color-charcoal-700": "#15151d",
            "app-mode-go-bg": "#2a8a55",
        }
        payload = W(name="smoke-test", overrides=overrides)
        _expect_ok(payload, f"wrote {payload.get('tokens_written')} tokens")
        if smoke_a.exists():
            _ok(f"file present at {smoke_a}")
            content = smoke_a.read_text()
            if all(f"--{k}: {v};" in content for k, v in overrides.items()):
                _ok("all override lines present in file")
            else:
                _bad("missing override lines in file")
        else:
            _bad(f"file missing: {smoke_a}")

        _label("apply_theme(first apply)")
        _expect_ok(A("smoke-test"), "applied smoke-test")
        text = style.read_text()
        if (
            "/* hermes-comfyui-theme-maker:active */" in text
            and "@import './themes/smoke-test.css';" in text
            and "/* hermes-comfyui-theme-maker:end */" in text
        ):
            _ok("sentinel block injected into style.css")
        else:
            _bad("sentinel block missing or malformed")

        _label("apply_theme(re-apply is idempotent)")
        text_a = style.read_text()
        A("smoke-test")
        if style.read_text() == text_a:
            _ok("re-apply produced identical file")
        else:
            _bad("re-apply changed style.css")

        _label("apply_theme(swap to a second theme)")
        W(name="smoke-test-2", overrides={"color-charcoal-800": "#101010"})
        A("smoke-test-2")
        text = style.read_text()
        if (
            text.count("/* hermes-comfyui-theme-maker:active */") == 1
            and "@import './themes/smoke-test-2.css';" in text
            and "@import './themes/smoke-test.css';" not in text
        ):
            _ok("swapped active theme; only one sentinel block")
        else:
            _bad("swap left stale state")

        _label("apply_theme(missing theme)")
        _expect_error(A("does-not-exist"), "rejects missing theme file")

        _label("render_theme_swatch(valid)")
        payload = S("smoke-test-2")
        if (
            payload.get("ok")
            and payload.get("tokens_in_theme")
            and "\033[48;2;" in payload.get("swatch", "")
        ):
            _ok(
                f"rendered swatch ({payload['tokens_in_theme']} tokens, "
                f"{len(payload['swatch'])} bytes of ANSI)"
            )
        else:
            _bad(f"unexpected swatch payload: {payload!r}")

        _label("render_theme_swatch(missing theme)")
        _expect_error(S("does-not-exist"), "rejects missing theme file")

        _label("render_theme_image(valid)")
        out_image = Path("~/Temp/smoke-test-image.png").expanduser()
        out_image.unlink(missing_ok=True)
        payload = I("smoke-test-2", output_path=str(out_image))
        if (
            payload.get("ok")
            and payload.get("size") == "1080x1080"
            and out_image.exists()
            and out_image.stat().st_size > 1000
        ):
            _ok(f"wrote {out_image.stat().st_size} bytes to {out_image}")
        else:
            _bad(f"unexpected image payload: {payload!r}")
        out_image.unlink(missing_ok=True)

        _label("render_theme_image(missing theme)")
        _expect_error(I("does-not-exist"), "rejects missing theme file")

    finally:
        print("\n[cleanup] reverting style.css and removing test theme files")
        style.write_text(style_before)
        smoke_a.unlink(missing_ok=True)
        smoke_b.unlink(missing_ok=True)
        print("          done")

    print(f"\nresults: {_PASS} pass, {_FAIL} fail")
    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
