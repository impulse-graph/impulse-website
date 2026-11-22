"""MkDocs build hooks for Impulse Graph Engine documentation (`www.impulsegraph.org`).

Registered in ``mkdocs.yml`` via::

    hooks:
      - scripts/mkdocs_hooks.py

On ``on_post_build``:
1. Emits static HTML redirect stubs for relocated Getting Started snapshot-builder URLs.
2. Generates ``site/llms.txt``, ``site/llms-full.txt``, and raw ``site/ai/SKILL.md``.
"""

from __future__ import annotations

import html
import importlib.util
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("mkdocs.hooks.impulse")

# Legacy URL path (relative to site_dir) -> (relative redirect target, canonical URL suffix)
LEGACY_REDIRECTS: dict[str, tuple[str, str]] = {
    "getting-started/building-snapshots/index.html": (
        "../../ecosystems/java/building-snapshots/",
        "ecosystems/java/building-snapshots/",
    ),
    "getting-started/snapshot-builder-reference/index.html": (
        "../../ecosystems/python/snapshots-from-parquet-csv/",
        "ecosystems/python/snapshots-from-parquet-csv/",
    ),
}


def _render_redirect_html(rel_target: str, canonical_url: str) -> str:
    esc_rel = html.escape(rel_target, quote=True)
    esc_canon = html.escape(canonical_url, quote=True)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Redirecting…</title>
  <link rel="canonical" href="{esc_canon}">
  <meta http-equiv="refresh" content="0; url={esc_rel}">
  <meta name="robots" content="noindex">
  <script>
    (function() {{
      var target = "{esc_rel}" + (window.location.search || "") + (window.location.hash || "");
      window.location.replace(target);
    }})();
  </script>
</head>
<body>
  <p>This page has moved to <a href="{esc_rel}">{esc_canon}</a>.</p>
</body>
</html>
"""


def _load_llms_generator():
    script_path = Path(__file__).resolve().parent / "generate_llms_txt.py"
    spec = importlib.util.spec_from_file_location("impulse_generate_llms_txt", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def on_post_build(config: dict[str, Any], **kwargs: Any) -> None:
    del kwargs
    site_dir = Path(config["site_dir"]).resolve()
    config_file_path = Path(config.get("config_file_path") or (Path(__file__).resolve().parent.parent / "mkdocs.yml")).resolve()
    website_dir = config_file_path.parent
    site_url = str(config.get("site_url") or "https://www.impulsegraph.org").rstrip("/")

    # 1. Write static HTML redirects for relocated legacy URLs
    for legacy_rel_html, (rel_target, canonical_suffix) in LEGACY_REDIRECTS.items():
        dest_file = site_dir / legacy_rel_html
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        canonical_url = f"{site_url}/{canonical_suffix.lstrip('/')}"
        dest_file.write_text(_render_redirect_html(rel_target, canonical_url), encoding="utf-8")
        log.info("Wrote legacy redirect %s -> %s", legacy_rel_html, rel_target)

    # 2. Generate llms.txt, llms-full.txt, and raw ai/SKILL.md
    generator = _load_llms_generator()
    outputs = generator.generate(
        website_dir=website_dir,
        site_dir=site_dir,
        config_filename=config_file_path.name,
    )
    log.info(
        "Generated LLM artifacts: %s (%d B), %s (%d B), %s",
        outputs["llms_txt"].name,
        outputs["llms_txt"].stat().st_size,
        outputs["llms_full_txt"].name,
        outputs["llms_full_txt"].stat().st_size,
        outputs["skill_md"].relative_to(site_dir),
    )
