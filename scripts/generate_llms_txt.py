#!/usr/bin/env python3
"""Generate machine-readable LLM documentation artifacts for Impulse Graph Engine.

Produces three artifacts inside MkDocs ``site_dir``:
1. ``llms.txt``       — Compact index adhering to https://llmstxt.org/
2. ``llms-full.txt``  — Single-file concatenation of all navigated docs + SKILL.md
3. ``ai/SKILL.md``    — Raw Markdown copy of docs/ai/SKILL.md for direct curl download
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml


class MkDocsYamlLoader(yaml.SafeLoader):
    """YAML SafeLoader that tolerates MkDocs/PyMdownX ``!`` and ``!!python/...`` tags."""


def _ignore_unknown_yaml_tag(
    loader: yaml.SafeLoader, tag_suffix: str, node: yaml.Node
) -> Any:
    del tag_suffix
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return None


MkDocsYamlLoader.add_multi_constructor("!", _ignore_unknown_yaml_tag)
MkDocsYamlLoader.add_multi_constructor("tag:yaml.org,2002:python/", _ignore_unknown_yaml_tag)


_FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)
_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def load_mkdocs_config(config_path: Path) -> dict[str, Any]:
    with config_path.open("r", encoding="utf-8") as fh:
        data = yaml.load(fh, Loader=MkDocsYamlLoader)
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML mapping in {config_path}, got {type(data).__name__}")
    return data


def strip_frontmatter(markdown_text: str) -> str:
    return _FRONTMATTER_RE.sub("", markdown_text, count=1)


def clean_inline_markdown(text: str) -> str:
    text = _MD_LINK_RE.sub(r"\1", text)
    text = _HTML_TAG_RE.sub("", text)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_title_and_summary(md_path: Path, fallback_title: str) -> tuple[str, str]:
    raw = md_path.read_text(encoding="utf-8")
    body = strip_frontmatter(raw)

    h1_match = _H1_RE.search(body)
    title = clean_inline_markdown(h1_match.group(1)) if h1_match else fallback_title

    lines = body.splitlines()
    in_fence = False
    in_indented_block = False
    paragraph_lines: list[str] = []

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            if paragraph_lines:
                break
            continue
        if in_fence:
            continue

        if stripped.startswith(("!!! ", "??? ", "=== ")):
            in_indented_block = True
            if paragraph_lines:
                break
            continue

        if in_indented_block:
            if not stripped or line.startswith(("    ", "\t")):
                continue
            in_indented_block = False

        if not stripped:
            if paragraph_lines:
                break
            continue

        if (
            stripped.startswith("#")
            or stripped.startswith("---")
            or stripped.startswith("|")
            or stripped.startswith("![")
            or stripped.startswith("<")
            or stripped.startswith(">")
            or stripped.startswith(("* ", "- ", "+ "))
            or re.match(r"^\d+\.\s", stripped)
        ):
            if paragraph_lines:
                break
            continue

        paragraph_lines.append(stripped)

    summary = clean_inline_markdown(" ".join(paragraph_lines))
    if len(summary) > 220:
        cutoff = summary[:217].rsplit(" ", 1)[0]
        summary = f"{cutoff}..."
    return title, summary


def doc_rel_to_canonical_url(
    rel_path: str, site_url: str, use_directory_urls: bool = True
) -> str:
    base = site_url.rstrip("/")
    norm = rel_path.lstrip("/")
    if norm == "index.md":
        return f"{base}/"
    if norm.endswith("/index.md"):
        prefix = norm[: -len("index.md")]
        return f"{base}/{prefix}"
    if norm.endswith(".md"):
        stem = norm[: -len(".md")]
        return f"{base}/{stem}/" if use_directory_urls else f"{base}/{stem}.html"
    return f"{base}/{norm}"


def collect_nav_sections(
    nav: list[Any],
) -> list[tuple[str, list[tuple[str, str]]]]:
    """Return ``[(section_name, [(nav_label, rel_md_path), ...]), ...]``."""
    sections: list[tuple[str, list[tuple[str, str]]]] = []
    root_items: list[tuple[str, str]] = []

    def _walk_items(node: Any, prefix: str = "") -> list[tuple[str, str]]:
        collected: list[tuple[str, str]] = []
        if isinstance(node, str):
            if node.endswith(".md"):
                collected.append((prefix or node, node))
        elif isinstance(node, list):
            for elem in node:
                collected.extend(_walk_items(elem, prefix=prefix))
        elif isinstance(node, dict):
            for label, val in node.items():
                qualified = f"{prefix} — {label}" if prefix else str(label)
                if isinstance(val, str):
                    if val.endswith(".md"):
                        collected.append((qualified, val))
                else:
                    collected.extend(_walk_items(val, prefix=qualified))
        return collected

    for entry in nav:
        if isinstance(entry, str) and entry.endswith(".md"):
            root_items.append((entry, entry))
        elif isinstance(entry, dict):
            for top_label, children in entry.items():
                if isinstance(children, str) and children.endswith(".md"):
                    root_items.append((str(top_label), children))
                else:
                    items = _walk_items(children, prefix="")
                    if items:
                        sections.append((str(top_label), items))

    if root_items:
        sections.insert(0, ("Overview", root_items))
    return sections


def generate(
    website_dir: Path,
    site_dir: Path,
    config_filename: str = "mkdocs.yml",
) -> dict[str, Path]:
    config_path = website_dir / config_filename
    cfg = load_mkdocs_config(config_path)

    site_name = str(cfg.get("site_name", "Impulse Graph Engine"))
    site_url = str(cfg.get("site_url", "https://www.impulsegraph.org")).rstrip("/")
    docs_dir = website_dir / str(cfg.get("docs_dir", "docs"))
    use_directory_urls = bool(cfg.get("use_directory_urls", True))
    nav = cfg.get("nav", [])

    site_dir.mkdir(parents=True, exist_ok=True)
    sections = collect_nav_sections(nav if isinstance(nav, list) else [])

    # Build llms.txt following https://llmstxt.org/
    llms_lines: list[str] = [
        f"# {site_name}",
        "",
        (
            "> Impulse Graph Engine (`impulse-graph` / `org.impulsegraph`) is a read-only, "
            "memory-mapped C-ABI binary snapshot graph engine (`.imps`) and 64-register "
            "bytecode virtual machine (`ImpulseVM` executing `impOps`) for Java 21/25 (Pure FFM, "
            "zero JNI), Python/PyTorch, C/C++20, Rust, Go, .NET, and Node.js."
        ),
        "",
        "Key architectural invariants for code generation and system design:",
        "",
        (
            "- **Immutable `.imps` Snapshots (No OLTP Mutations)**: Snapshots are read-only "
            "memory-mapped files (`mmap`); never emit `CREATE`/`MERGE`/`INSERT`/`SET`/`DELETE` "
            "mutations. Rebuild `.imps` artifacts via `impulse-graph build` or Java "
            "`SnapshotBuilder` and rotate atomically via `SnapshotLifecycleManager` / "
            "`SnapshotSwapManager`."
        ),
        (
            "- **Per-Domain Dense ID Independence (`0 .. N_d - 1`)**: There is no global node ID "
            "space (`User#0 != Account#0`). Always anchor queries to an explicit domain "
            "(`snap.domain(\"User\")` or generated typed views) and persist external business "
            "keys (`fromKey` / `toKeyList`), never ephemeral dense IDs."
        ),
        (
            "- **Engine-Native Kleisli Set Traversals**: Never write client-side imperative "
            "`for` loops performing point lookups hop-by-hop. Express multi-hop CSR/CSC walks, "
            "CEL filters, monoid reductions (`SUM`/`MIN`/`MAX`), and `repeatUntilStable` loops "
            "in a single engine pipeline or prepared `openCypher` / `ImpLog` / `ImpK` query."
        ),
        "",
        "## AI Coding Agent & Machine-Readable Resources",
        "",
        (
            f"- [AI Coding Agent Skill & Rules (SKILL.md)]({site_url}/ai/SKILL.md): "
            "Self-contained raw Markdown skill/rules pack for Claude Code, Antigravity, Cursor, "
            "and GitHub Copilot."
        ),
        (
            f"- [Full Documentation & Specification Corpus (llms-full.txt)]"
            f"({site_url}/llms-full.txt): Single-file concatenation of all Impulse Graph "
            "guides, SDK references, and normative `.imps` / `ImpulseVM` specifications."
        ),
        "",
    ]

    ordered_files: list[tuple[str, str]] = []
    seen_rel_paths: set[str] = set()

    for section_title, items in sections:
        section_entries: list[str] = []
        for nav_label, rel_path in items:
            md_file = docs_dir / rel_path
            if not md_file.is_file():
                continue
            url = doc_rel_to_canonical_url(rel_path, site_url, use_directory_urls)
            page_title, summary = extract_title_and_summary(md_file, nav_label)
            display_title = (
                f"{nav_label} ({page_title})"
                if " — " in nav_label and nav_label.split(" — ")[-1] != page_title
                else page_title
            )
            if summary:
                section_entries.append(f"- [{display_title}]({url}): {summary}")
            else:
                section_entries.append(f"- [{display_title}]({url})")

            if rel_path not in seen_rel_paths:
                seen_rel_paths.add(rel_path)
                ordered_files.append((rel_path, url))

        if section_entries:
            llms_lines.append(f"## {section_title}")
            llms_lines.append("")
            llms_lines.extend(section_entries)
            llms_lines.append("")

    llms_txt_path = site_dir / "llms.txt"
    llms_txt_path.write_text("\n".join(llms_lines).rstrip() + "\n", encoding="utf-8")

    # Copy docs/ai/SKILL.md verbatim to <site_dir>/ai/SKILL.md for raw curl downloads
    skill_rel = "ai/SKILL.md"
    skill_src = docs_dir / skill_rel
    skill_dst = site_dir / "ai" / "SKILL.md"
    if skill_src.is_file():
        skill_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(skill_src, skill_dst)
        if skill_rel not in seen_rel_paths:
            seen_rel_paths.add(skill_rel)
            ordered_files.insert(0, (skill_rel, f"{site_url}/ai/SKILL.md"))

    # Build llms-full.txt concatenating SKILL.md + all navigated docs in reading order
    separator = "=" * 80
    full_chunks: list[str] = [
        f"# {site_name} — Complete Documentation & Specification Corpus",
        f"# Source: {site_url}/llms-full.txt",
        f"# Index:  {site_url}/llms.txt",
        f"# Skill:  {site_url}/ai/SKILL.md",
        "",
    ]
    for rel_path, url in ordered_files:
        md_file = docs_dir / rel_path
        if not md_file.is_file():
            continue
        content = md_file.read_text(encoding="utf-8").rstrip()
        full_chunks.append(separator)
        full_chunks.append(f"FILE: docs/{rel_path} | URL: {url}")
        full_chunks.append(separator)
        full_chunks.append("")
        full_chunks.append(content)
        full_chunks.append("")

    llms_full_path = site_dir / "llms-full.txt"
    llms_full_path.write_text("\n".join(full_chunks).rstrip() + "\n", encoding="utf-8")

    return {
        "llms_txt": llms_txt_path,
        "llms_full_txt": llms_full_path,
        "skill_md": skill_dst,
    }


def main(argv: list[str] | None = None) -> int:
    default_website_dir = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description="Generate site/llms.txt, site/llms-full.txt, and site/ai/SKILL.md from mkdocs.yml."
    )
    parser.add_argument(
        "--website-dir",
        type=Path,
        default=default_website_dir,
        help="Path to impulse-website root directory containing mkdocs.yml (default: repo root).",
    )
    parser.add_argument(
        "--site-dir",
        type=Path,
        default=None,
        help="Target MkDocs output directory (default: <website-dir>/site).",
    )
    parser.add_argument(
        "--config-file",
        default="mkdocs.yml",
        help="MkDocs YAML filename relative to --website-dir (default: mkdocs.yml).",
    )
    args = parser.parse_args(argv)

    website_dir = args.website_dir.resolve()
    site_dir = (args.site_dir if args.site_dir is not None else website_dir / "site").resolve()

    outputs = generate(website_dir=website_dir, site_dir=site_dir, config_filename=args.config_file)
    print(
        f"[llms] Generated {outputs['llms_txt']} ({outputs['llms_txt'].stat().st_size:,} B), "
        f"{outputs['llms_full_txt']} ({outputs['llms_full_txt'].stat().st_size:,} B), "
        f"and {outputs['skill_md']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
