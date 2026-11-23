"""MkDocs build hooks for Impulse Graph Engine documentation (`www.impulsegraph.org`).

Registered in ``mkdocs.yml`` via::

    hooks:
      - scripts/mkdocs_hooks.py

On ``on_post_build``:
1. Emits static HTML redirect stubs for relocated Getting Started snapshot-builder URLs.
2. Generates ``site/llms.txt``, ``site/llms-full.txt``, and raw ``site/ai/SKILL.md``.
3. Verifies Markdown list indentation / fence balance and generated HTML ``<article>`` layout.
"""

from __future__ import annotations

import html
import importlib.util
import logging
import re
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

    # 3. Verify Markdown list indentation & generated HTML article layout
    _verify_markdown_and_html_layout(website_dir=website_dir, site_dir=site_dir)


_FENCE_RE = re.compile(r"^(\s*)(`{3,}|~{3,})")
_LIST_ITEM_RE = re.compile(r"^( +)(?:[-*]|\d+\.)\s+")
_RAW_P_LIST_RE = re.compile(r"\n\s*(?:\d+\.|[-*])\s+")
_RAW_ADMONITION_RE = re.compile(r"(?:^|\n)\s*!!!\s+\w+")
_RAW_TAB_RE = re.compile(r'(?:^|\n)\s*===\s+(?:"|&quot;)')


def _verify_markdown_and_html_layout(website_dir: Path, site_dir: Path) -> None:
    docs_dir = website_dir / "docs"
    errors: list[str] = []

    for md_path in sorted(docs_dir.rglob("*.md")):
        rel = md_path.relative_to(docs_dir)
        if rel.parts and rel.parts[0] == "design-notes":
            continue
        in_fence = False
        fence_char = ""
        fence_len = 0
        for lineno, line in enumerate(md_path.read_text(encoding="utf-8").splitlines(), 1):
            fm = _FENCE_RE.match(line)
            if fm:
                marker = fm.group(2)
                if not in_fence:
                    in_fence = True
                    fence_char = marker[0]
                    fence_len = len(marker)
                elif marker[0] == fence_char and len(marker) >= fence_len and line.strip() == marker:
                    in_fence = False
                continue
            if in_fence:
                continue

            lm = _LIST_ITEM_RE.match(line)
            if lm and (len(lm.group(1)) % 4 != 0):
                errors.append(
                    f"docs/{rel}:{lineno}: list item indented by {len(lm.group(1))} spaces "
                    f"(Python-Markdown requires multiples of 4 spaces): {line.strip()[:80]}"
                )

        if in_fence:
            errors.append(f"docs/{rel}: unclosed code fence ({fence_char * fence_len}) at end of file")

    checked_html = 0
    for html_path in sorted(site_dir.rglob("*.html")):
        rel = html_path.relative_to(site_dir)
        if rel.parts and rel.parts[0] in {"javadoc", "doxygen", "assets", "design-notes"}:
            continue
        text = html_path.read_text(encoding="utf-8", errors="ignore")
        m_art = re.search(r"<article[^>]*>(.*?)</article>", text, re.S)
        if not m_art:
            continue
        checked_html += 1
        prose = re.sub(r"<pre[^>]*>.*?</pre>", "", m_art.group(1), flags=re.S)
        prose = re.sub(r"<code[^>]*>.*?</code>", "", prose, flags=re.S)

        if "```" in prose:
            errors.append(f"site/{rel}: raw '```' code fence rendered in HTML prose")
        if _RAW_ADMONITION_RE.search(prose):
            errors.append(f"site/{rel}: unparsed '!!!' admonition rendered in HTML prose")
        if _RAW_TAB_RE.search(prose):
            errors.append(f"site/{rel}: unparsed '===' content tab rendered in HTML prose")

        for pm in re.finditer(r"<p>(.*?)</p>", prose, re.S):
            p_body = pm.group(1)
            if _RAW_P_LIST_RE.search(p_body):
                snippet = re.sub(r"\s+", " ", p_body).strip()[:100]
                errors.append(
                    f"site/{rel}: unparsed inline list inside <p> (missing blank line before list): {snippet}"
                )

    if errors:
        joined = "\n  - ".join(errors[:25])
        raise RuntimeError(f"Documentation layout verification failed ({len(errors)} issue(s)):\n  - {joined}")

    log.info("Verified Markdown indentation and HTML layout across %d generated pages.", checked_html)
