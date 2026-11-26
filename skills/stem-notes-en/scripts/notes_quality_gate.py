#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deterministic Quality Gate for STEM Notes, Vector Circuit Diagrams & Offline Quizzes.

Usage:
  python scripts/notes_quality_gate.py <file_or_dir> [...]
"""

import ipaddress
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse


SKIP_DIRS = {
    ".git",
    ".qoder",
    ".claude",
    ".cursor",
    ".codex",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
}

SKIP_MD_NAMES = {"skill.md", "readme.md", "readme_zh.md", "license", "license.md"}


def strip_tags(html_str: str) -> str:
    """Strip HTML tags and normalize whitespace for visual length checks."""
    text = re.sub(r"<[^>]+>", "", html_str)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&rarr;", "→")
        .replace("&rArr;", "⇒")
        .replace("&minus;", "−")
        .replace("&times;", "×")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
    )
    return re.sub(r"\s+", " ", text).strip()


def _parse_translate(transform_str: str) -> tuple[float, float]:
    if not transform_str:
        return 0.0, 0.0
    m = re.search(r"translate\(\s*([+-]?[0-9.]+)(?:[\s,]+([+-]?[0-9.]+))?\s*\)", transform_str)
    if not m:
        return 0.0, 0.0
    tx = float(m.group(1))
    ty = float(m.group(2)) if m.group(2) is not None else 0.0
    return tx, ty


def _extract_svg_text_boxes(clean_block: str) -> list[tuple[float, float, float, str, int]]:
    """Extract SVG <text> bounding estimates with accumulated translate() offsets."""
    boxes: list[tuple[float, float, float, str, int]] = []
    try:
        root = ET.fromstring(clean_block)
    except ET.ParseError:
        text_nodes = re.findall(r"<text\b([^>]*)>(.*?)</text>", clean_block, flags=re.DOTALL | re.IGNORECASE)
        for attrs, inner in text_nodes:
            plain = strip_tags(inner)
            word_count = len(plain.split())
            xm = re.search(r'\bx\s*=\s*["\']([+-]?[0-9.]+)["\']', attrs)
            ym = re.search(r'\by\s*=\s*["\']([+-]?[0-9.]+)["\']', attrs)
            anchor_m = re.search(r'\btext-anchor\s*=\s*["\'](\w+)["\']', attrs)
            if xm and ym:
                x_val = float(xm.group(1))
                y_val = float(ym.group(1))
                anchor = anchor_m.group(1) if anchor_m else "start"
                w_est = len(plain) * 6.5
                if anchor == "middle":
                    x0, x1 = x_val - w_est / 2.0, x_val + w_est / 2.0
                elif anchor == "end":
                    x0, x1 = x_val - w_est, x_val
                else:
                    x0, x1 = x_val, x_val + w_est
                boxes.append((x0, x1, y_val, plain, word_count))
            else:
                boxes.append((0.0, 0.0, -9999.0, plain, word_count))
        return boxes

    def walk(elem: ET.Element, ox: float, oy: float) -> None:
        dx, dy = _parse_translate(elem.attrib.get("transform", ""))
        cx, cy = ox + dx, oy + dy
        tag_local = elem.tag.split("}")[-1].lower()
        if tag_local == "text":
            plain = re.sub(r"\s+", " ", "".join(elem.itertext())).strip()
            word_count = len(plain.split())
            x_attr = elem.attrib.get("x")
            y_attr = elem.attrib.get("y")
            if x_attr is not None and y_attr is not None:
                try:
                    x_val = cx + float(x_attr.split()[0])
                    y_val = cy + float(y_attr.split()[0])
                    anchor = elem.attrib.get("text-anchor", "start")
                    fs_raw = elem.attrib.get("font-size", "12")
                    fs_m = re.search(r"[0-9.]+", fs_raw)
                    fs = float(fs_m.group(0)) if fs_m else 12.0
                    scale = fs / 12.0
                    w_est = len(plain) * 6.2 * scale
                    if anchor == "middle":
                        x0, x1 = x_val - w_est / 2.0, x_val + w_est / 2.0
                    elif anchor == "end":
                        x0, x1 = x_val - w_est, x_val
                    else:
                        x0, x1 = x_val, x_val + w_est
                    boxes.append((x0, x1, y_val, plain, word_count))
                except ValueError:
                    boxes.append((0.0, 0.0, -9999.0, plain, word_count))
            else:
                boxes.append((0.0, 0.0, -9999.0, plain, word_count))
            return
        for child in elem:
            walk(child, cx, cy)

    walk(root, 0.0, 0.0)
    return boxes


def check_hygiene_and_offline(content: str, filepath: str) -> list[str]:
    """Verify zero local absolute paths, zero loopback URLs, and zero private embed tags."""
    errors: list[str] = []
    for url in re.findall(r"https?://[^\s\"'<>`)]+", content, flags=re.IGNORECASE):
        try:
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
            is_loop = host == ("local" + "host")
            if not is_loop and host:
                try:
                    is_loop = ipaddress.ip_address(host).is_loopback
                except ValueError:
                    is_loop = False
            if is_loop:
                errors.append(
                    f"[OFFLINE_VIOLATION] {filepath}: Loopback URL `{url}` found; deliverables must be 100% offline."
                )
        except Exception:
            pass

    file_scheme = "fi" + "le:///"
    if file_scheme in content.lower():
        errors.append(f"[ABSOLUTE_PATH_LEAK] {filepath}: Found `{file_scheme}` absolute link; use relative paths.")
    win_user_pat = re.compile(r"[A-Za-z]:\\+" + "Us" + r"ers\\", flags=re.IGNORECASE)
    mac_user_pat = re.compile(r"(?:^|[\s\"'(])/" + "Us" + r"ers/", flags=re.IGNORECASE)
    if win_user_pat.search(content) or mac_user_pat.search(content):
        errors.append(f"[LOCAL_PATH_LEAK] {filepath}: Found local home directory path; use relative paths.")

    private_embed = "<" + "agent" + "-embed"
    if private_embed in content.lower():
        errors.append(f"[NONSTANDARD_EMBED] {filepath}: Found non-standard embed tag; use standalone HTML links.")

    return errors


def check_svg_purity(content: str, filepath: str) -> list[str]:
    """Validate pure SVG tags, concise labels, single deterministic topology, and zero overlap."""
    errors: list[str] = []
    no_style = re.sub(r"<style\b[^>]*>.*?</style>", "", content, flags=re.DOTALL | re.IGNORECASE)
    no_script = re.sub(r"<script\b[^>]*>.*?</script>", "", no_style, flags=re.DOTALL | re.IGNORECASE)
    no_comments = re.sub(r"<!--.*?-->", "", no_script, flags=re.DOTALL)
    svg_blocks = re.findall(r"<svg\b[^>]*>.*?</svg>", no_comments, flags=re.DOTALL | re.IGNORECASE)
    for idx, block in enumerate(svg_blocks, 1):
        clean_block = re.sub(r"<!--.*?-->", "", block, flags=re.DOTALL)
        bad_tags = re.findall(r"<(i|b|sub|sup|span|div)\b[^>]*>", clean_block, flags=re.IGNORECASE)
        if bad_tags:
            uniq = sorted(set(t.lower() for t in bad_tags))
            errors.append(
                f"[SVG_HTML_POLLUTION] {filepath} (svg #{idx}): Disallowed HTML tags {uniq} inside <svg>; use <tspan>."
            )

        boxes = _extract_svg_text_boxes(clean_block)
        valid_boxes = []
        for x0, x1, y_val, plain, word_count in boxes:
            if word_count > 6:
                errors.append(
                    f"[SVG_VERBOSE_LABEL] {filepath}: <text> `{plain}` has {word_count} words (max 6); move prose to .legend-bar."
                )
            if re.search(r"(?:\(\s*or\s+|\boptional\b)", plain, flags=re.IGNORECASE):
                errors.append(
                    f"[SVG_AMBIGUOUS_TOPOLOGY] {filepath}: <text> `{plain}` mixes optional topologies; split into separate figures."
                )
            if y_val > -9000.0 and plain:
                valid_boxes.append((x0, x1, y_val, plain))

        for i in range(len(valid_boxes)):
            x0_a, x1_a, y_a, txt_a = valid_boxes[i]
            for j in range(i + 1, len(valid_boxes)):
                x0_b, x1_b, y_b, txt_b = valid_boxes[j]
                if abs(y_a - y_b) < 11.0 and max(x0_a, x0_b) < min(x1_a, x1_b) - 3.0:
                    errors.append(
                        f"[SVG_TEXT_OVERLAP] {filepath}: Labels `{txt_a}` (y={y_a:.1f}) and `{txt_b}` (y={y_b:.1f}) overlap."
                    )

    return errors


def check_raw_math_in_html(content: str, filepath: str) -> list[str]:
    """Ensure rendered HTML uses print-grade sup/sub/.frac rather than raw ^, _, or LaTeX macros."""
    errors: list[str] = []
    no_style = re.sub(r"<style\b[^>]*>.*?</style>", "", content, flags=re.DOTALL | re.IGNORECASE)
    no_script = re.sub(r"<script\b[^>]*>.*?</script>", "", no_style, flags=re.DOTALL | re.IGNORECASE)
    no_comments = re.sub(r"<!--.*?-->", "", no_script, flags=re.DOTALL)

    latex_leaks = re.findall(
        r"\\(?:frac|varepsilon|varphi|partial|infty|pi|theta|sigma|omega|lambda|beta|alpha|mu)\b",
        no_comments,
    )
    if latex_leaks:
        errors.append(
            f"[HTML_LATEX_LEAK] {filepath}: Unescaped LaTeX macros {sorted(set(latex_leaks))} found in HTML."
        )

    text_only = re.sub(r"<[^>]+>", " ", no_comments)
    carets = re.findall(r"[A-Za-z0-9\)\]]\^[A-Za-z0-9\(\-\+]", text_only)
    if carets:
        errors.append(f"[HTML_RAW_EXPONENT] {filepath}: Raw `^` notation {carets[:5]}; use <sup>...</sup>.")

    raw_subs = re.findall(r"\b(?:[QERDVUCPfuzIRriAvεφσλ]_(?:\{[0-9a-zA-Z'\+\-]+\}|[0-9a-zA-Z'\+]{1,3}))\b", text_only)
    if raw_subs:
        errors.append(f"[HTML_RAW_SUBSCRIPT] {filepath}: Raw `_` notation {raw_subs[:5]}; use <sub>...</sub>.")

    return errors


def validate_diagram_html(content: str, filepath: str) -> list[str]:
    """Gate D: Validate standalone vector diagram HTML."""
    errors: list[str] = []
    errors.extend(check_hygiene_and_offline(content, filepath))
    errors.extend(check_svg_purity(content, filepath))
    errors.extend(check_raw_math_in_html(content, filepath))

    no_comments = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
    forbidden_classes = re.findall(
        r"class\s*=\s*['\"][^'\"]*\b(info-col|text-col|desc-col|right-panel|formula-card)\b[^'\"]*['\"]",
        no_comments,
    )
    if forbidden_classes:
        errors.append(
            f"[DIAGRAM_SIDEBAR_DISALLOWED] {filepath}: Disallowed sidebar classes {sorted(set(forbidden_classes))}; use .legend-bar below canvas."
        )
    if "<svg" not in no_comments.lower():
        errors.append(f"[DIAGRAM_MISSING_SVG] {filepath}: Diagram HTML must include an <svg> element.")
    return errors


def validate_board_html(content: str, filepath: str) -> list[str]:
    """Gate B: Validate three-in-one study review board HTML."""
    errors: list[str] = []
    errors.extend(check_hygiene_and_offline(content, filepath))
    errors.extend(check_svg_purity(content, filepath))
    errors.extend(check_raw_math_in_html(content, filepath))

    no_comments = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
    no_comments = re.sub(r"/\*.*?\*/", "", no_comments, flags=re.DOTALL)
    no_scripts = re.sub(r"<script\b[^>]*>.*?</script>", "", no_comments, flags=re.DOTALL | re.IGNORECASE)

    bad_quotes = re.findall(r'\b(?:class|id|style|for|type|name|data-\w+)\s*=\s*(?:"[^"\n>]*\'|\'[^\'\n>]*")', no_scripts)
    if bad_quotes:
        errors.append(f"[HTML_QUOTE_MISMATCH] {filepath}: Mismatched attribute quotes `{bad_quotes[:3]}`.")

    empty_grids = re.findall(r'<div[^>]*class="[^"]*flashcard-grid[^"]*"[^>]*>\s*</div>', no_scripts)
    if empty_grids:
        errors.append(f"[BOARD_EMPTY_FLASHCARDS] {filepath}: Empty `.flashcard-grid`; flashcards must be statically pre-rendered.")

    static_fcards = re.findall(r'class="[^"]*\bfcard-front\b[^"]*"', no_scripts)
    fc_chks = re.findall(r'class="[^"]*\bfc-chk\b[^"]*"', no_scripts)
    if len(static_fcards) < 2:
        errors.append(f"[BOARD_TOO_FEW_CARDS] {filepath}: Found {len(static_fcards)} static flashcards (minimum 2).")
    if len(fc_chks) < len(static_fcards):
        errors.append(f"[BOARD_MISSING_CHECKBOX] {filepath}: Fewer `.fc-chk` inputs than flashcards.")
    if "tab-rad" not in no_scripts:
        errors.append(f"[BOARD_MISSING_CSS_TABS] {filepath}: Missing pure-CSS `.tab-rad` tab radio controls.")

    return errors


def validate_quiz_html(content: str, filepath: str) -> list[str]:
    """Gate Q: Validate offline interactive variant quiz HTML."""
    errors: list[str] = []
    errors.extend(check_hygiene_and_offline(content, filepath))
    errors.extend(check_svg_purity(content, filepath))
    errors.extend(check_raw_math_in_html(content, filepath))

    no_comments = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
    no_comments_css = re.sub(r"/\*.*?\*/", "", no_comments, flags=re.DOTALL)

    if re.search(r"\b(?:fetch\s*\(|XMLHttpRequest|navigator\.sendBeacon)\b", no_comments):
        errors.append(f"[QUIZ_NETWORK_DISALLOWED] {filepath}: Offline quiz must not call fetch / XMLHttpRequest / sendBeacon.")
    if "localStorage" not in no_comments:
        errors.append(f"[QUIZ_MISSING_LOCALSTORAGE] {filepath}: Missing `localStorage` persistence for answers and mistake notebook.")
    if "q-fig" in no_comments and "q-body-row" not in no_comments_css:
        errors.append(f"[QUIZ_LAYOUT_MISSING_ROW] {filepath}: Uses `.q-fig` without `.q-body-row` side-by-side layout.")
    if not re.search(r"\.opts-list\s*\{[^}]*grid-template-columns\s*:\s*1fr\s+1fr", no_comments_css):
        errors.append(f"[QUIZ_GRID_VIOLATION] {filepath}: `.opts-list` must use `grid-template-columns: 1fr 1fr`.")
    if "is-unknown" not in no_comments or "unknown-btn" not in no_comments:
        errors.append(f"[QUIZ_MISSING_UNKNOWN_BTN] {filepath}: Missing `.is-unknown` / `.unknown-btn` control.")
    if not re.search(r"pointer-events\s*:\s*none", no_comments_css):
        errors.append(f"[QUIZ_MISSING_LOCK] {filepath}: Missing CSS `pointer-events: none` immutable answer lock.")

    panels = re.findall(
        r'<div\s+class="q-panel"\s+id="panel-q(\d+)"[^>]*>(.*?)<div\s+class="foot-nav"',
        no_comments,
        flags=re.DOTALL,
    )
    if not panels:
        errors.append(f"[QUIZ_MISSING_PANELS] {filepath}: No statically pre-rendered `.q-panel` nodes found.")
        return errors

    for q_num, panel_html in panels:
        stem_match = re.search(r'<div\s+class="q-stem"[^>]*>(.*?)</div>', panel_html, flags=re.DOTALL)
        stem_text = strip_tags(stem_match.group(1)) if stem_match else ""
        if stem_text and re.search(r"(?:previous\s+question|from\s+question\s+\d+|as\s+in\s+q\d+)", stem_text, flags=re.IGNORECASE):
            errors.append(f"[QUIZ_CROSS_REF] {filepath} Q{q_num}: Questions must be self-contained.")
        if "hint-box" in panel_html:
            errors.append(f"[QUIZ_HINT_LEAK] {filepath} Q{q_num}: Disallowed `hint-box` inside question stem.")

        fig_match = re.search(r'<div\s+class="q-fig"[^>]*>(.*?)</div>', panel_html, flags=re.DOTALL)
        if fig_match:
            if "<svg" not in fig_match.group(1).lower():
                errors.append(f"[QUIZ_FIG_MISSING_SVG] {filepath} Q{q_num}: `.q-fig` must contain an `<svg>`.")
        else:
            if stem_text and re.search(r"\b(?:amplifier\s+circuit|bias\s+circuit|common-emitter|common-source|op-amp|shown.*circuit)\b", stem_text, flags=re.IGNORECASE):
                errors.append(
                    f"[QUIZ_CIRCUIT_MISSING_FIG] {filepath} Q{q_num}: Circuit topology question must include a `.q-fig` SVG schematic."
                )

        opts = re.findall(r'<span\s+class="opt-text"[^>]*>(.*?)</span>', panel_html, flags=re.DOTALL)
        if len(opts) != 4:
            errors.append(f"[QUIZ_OPTION_COUNT] {filepath} Q{q_num}: Found {len(opts)} options (expected 4).")
            continue

        clean_opts = [strip_tags(o) for o in opts]
        lengths = [len(t) for t in clean_opts]
        min_l, max_l = min(lengths), max(lengths)
        if max_l > min_l * 2.5 + 16:
            errors.append(
                f"[QUIZ_OPTION_IMBALANCE] {filepath} Q{q_num}: Option lengths too unbalanced (min {min_l} vs max {max_l})."
            )
        parens_count = sum(1 for t in clean_opts if "(" in t and ")" in t and len(re.findall(r"\([^)]{6,}\)", t)) > 0)
        if parens_count == 1:
            errors.append(
                f"[QUIZ_PAREN_SPOILER] {filepath} Q{q_num}: Only 1 option has explanatory parentheses; remove to prevent spoilers."
            )

    return errors


def validate_markdown_note(content: str, filepath: str) -> list[str]:
    """Gate M: Validate Markdown + LaTeX study notes."""
    errors: list[str] = []
    errors.extend(check_hygiene_and_offline(content, filepath))

    bad_prime = re.findall(r"\$[^$\n]+'\$(?=[（，。、；：）》.,;:\)])", content)
    if bad_prime:
        errors.append(f"[MD_PRIME_LEAK] {filepath}: Use `\\prime$` instead of raw `'$` in `{bad_prime[:3]}`.")
    if re.search(r"\\(?:multicolumn|multirow)\b", content):
        errors.append(f"[MD_TABLE_MACRO] {filepath}: GFM tables do not support `\\multicolumn` or `\\multirow`.")

    for lineno, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.count("|") >= 2):
            continue
        clean_line = re.sub(r"`[^`\n]*`", "", stripped).replace(r"\$", "").replace(r"\|", "")
        cells = clean_line.strip("|").split("|")
        odd_cells = [c.strip() for c in cells if len(re.findall(r"(?<!\\)\$", c)) % 2 == 1]
        if odd_cells:
            errors.append(
                f"[MD_TABLE_PIPE_SPLIT] {filepath} line {lineno}: Use `\\vert` instead of bare `|` inside GFM table math."
            )
    return errors


def collect_targets(root: Path) -> list[Path]:
    """Collect .html and .md study files while skipping hidden tool directories."""
    if root.is_file():
        return [root]
    targets: list[Path] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel_parts = set(p.relative_to(root).parts[:-1])
        if rel_parts & SKIP_DIRS:
            continue
        if p.suffix.lower() == ".md":
            if p.name.lower() in SKIP_MD_NAMES:
                continue
            targets.append(p)
        elif p.suffix.lower() == ".html":
            targets.append(p)
    return targets


def check_file(target: Path) -> list[str]:
    """Route target file to the appropriate validator."""
    if not target.exists():
        return [f"[FILE_NOT_FOUND] {target}"]

    name = target.name.lower()
    content = target.read_text(encoding="utf-8", errors="replace")

    if target.suffix.lower() == ".md":
        if name in SKIP_MD_NAMES:
            return []
        return validate_markdown_note(content, str(target))

    if target.suffix.lower() == ".html":
        if "board" in name:
            return validate_board_html(content, str(target))
        if "quiz" in name:
            return validate_quiz_html(content, str(target))
        if any(k in name for k in ("fig", "diagram", "svg", "circuit", "mod", "step")):
            return validate_diagram_html(content, str(target))
        return check_hygiene_and_offline(content, str(target)) + check_raw_math_in_html(content, str(target))

    return []


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    if len(sys.argv) < 2:
        print("Usage: python notes_quality_gate.py <file_or_dir> [...]")
        return 1

    total_errors: list[str] = []
    checked_files: list[Path] = []
    for arg in sys.argv[1:]:
        p = Path(arg)
        if not p.exists():
            total_errors.append(f"[PATH_NOT_FOUND] {p}")
            continue
        targets = collect_targets(p)
        if p.is_dir() and not targets:
            total_errors.append(f"[NO_TARGETS] {p}: No .html or .md study deliverables found.")
            continue
        for t in targets:
            checked_files.append(t)
            total_errors.extend(check_file(t))

    if total_errors:
        print(f"FAILED [NOTES QUALITY GATE]: Checked {len(checked_files)} file(s), found {len(total_errors)} violation(s):")
        for err in total_errors:
            print(f"  - {err}")
        return 1

    print(f"PASSED [NOTES QUALITY GATE]: All {len(checked_files)} file(s) passed deterministic validation!")
    for f in checked_files:
        print(f"  OK {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
