#!/usr/bin/env python3
"""check_css_wiring.py — CSS class selectors must be wired to markup (2600r12).

THE DEFECT THIS EXISTS FOR (ledger R29/R36): 2600r10 shipped review-section
CSS for classes no template produced. In 2620 the new responsive authority files
were initially outside this gate, allowing the same defect class to recur in
admin-responsive.css. The gate now scans every shipped stylesheet.

WHAT IT DOES: extracts every class token used in CSS selectors, extracts the
class vocabulary actually present in PHP templates and JS (class="..."
attributes, classList operations, quoted class strings), and reports CSS
classes that no markup or script ever produces.

RATCHET, like check_wiring: legacy orphans predating this tool live in the
baseline file and are tolerated; any NEW orphan fails the build. Shrink the
baseline when legacy classes are cleaned up; never grow it to admit a new one.

Usage:
    python3 tools/check_css_wiring.py <site-root> [--update-baseline]

Exit 0 = no new orphans. Exit 1 = new orphans (listed). Static analysis only:
this proves a selector CAN match, never that the rendered result is right.
"""
import re
import sys
from pathlib import Path

BASELINE = 'tools/data/css-known-orphans.txt'

# Selector-side classes to ignore: states applied at runtime by JS in ways the
# extractor can miss, plus pseudo-ish utility hooks.
DYNAMIC_STATES = {
    'in', 'open', 'active', 'visible', 'hidden', 'show', 'hide', 'on', 'off',
    'is-open', 'is-active', 'loading', 'loaded', 'error', 'success', 'dragging',
    'drag-over', 'sorting', 'selected', 'expanded', 'collapsed', 'sticky',
    'stuck', 'js', 'no-js', 'touch', 'reveal-ready',
}

CLASS_IN_SELECTOR = re.compile(r'\.(-?[A-Za-z_][A-Za-z0-9_-]*)')
CLASS_ATTR = re.compile(r'class\s*=\s*(["\'])(.*?)\1', re.I | re.S)
JS_CLASSLIST = re.compile(r"classList\.(?:add|remove|toggle|replace)\(\s*['\"]([A-Za-z0-9_-]+)['\"]")
JS_STRING_CLASS = re.compile(r"['\"]((?:[A-Za-z0-9_-]+\s+)*[A-Za-z_-][A-Za-z0-9_-]*)['\"]")


def css_classes(css_text: str):
    """Class tokens used in selectors, comments stripped, declarations excluded."""
    code = re.sub(r'/\*.*?\*/', '', css_text, flags=re.S)
    out = set()
    # walk rule by rule: selector = text before each '{' back to '}' or ';'
    for m in re.finditer(r'([^{}]+)\{', code):
        sel = m.group(1)
        if '@' in sel and '{' not in sel.split('@')[-1]:
            # @media (...) { — the condition is not a selector
            if sel.strip().startswith('@'):
                continue
        for c in CLASS_IN_SELECTOR.findall(sel):
            out.add(c)
    return out


def markup_classes(root: Path):
    """Every class the templates or JS can actually put on an element."""
    vocab = set()
    for p in root.rglob('*.php'):
        if any(part in ('tools', 'tests', 'deploy', 'PHPMailer') for part in p.parts):
            continue
        text = p.read_text(encoding='utf-8', errors='replace')
        for _quote, attr in CLASS_ATTR.findall(text):
            # Capture literal class fragments inside PHP conditionals before
            # removing the PHP block. Example:
            # class="hero<?= $has ? ' hero--bleed' : '' ?>"
            for block in re.findall(r'<\?(?:php|=)(.*?)\?>', attr, flags=re.S):
                for literal in re.findall(r"['\"]([^'\"]*)['\"]", block):
                    vocab.update(t for t in literal.split()
                                 if re.fullmatch(r'-?[A-Za-z_][A-Za-z0-9_-]*', t))
            clean = re.sub(r'<\?(?:php|=).*?\?>', ' ', attr, flags=re.S)
            vocab.update(t for t in clean.split()
                         if re.fullmatch(r'-?[A-Za-z_][A-Za-z0-9_-]*', t))
        # class names emitted from PHP string expressions ("class fragments")
        for frag in re.findall(r"['\"]([A-Za-z_-][A-Za-z0-9 _-]*)['\"]\s*[.,)]", text):
            vocab.update(t for t in frag.split() if re.fullmatch(r'-?[A-Za-z_][A-Za-z0-9_-]*', t))
    for p in root.rglob('*.js'):
        if any(part in ('tools', 'tests', 'deploy') for part in p.parts):
            continue
        text = p.read_text(encoding='utf-8', errors='replace')
        vocab.update(JS_CLASSLIST.findall(text))
        for lit in JS_STRING_CLASS.findall(text):
            vocab.update(lit.split())
    return vocab


def main() -> int:
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2
    root = Path(argv[0]).resolve()
    update = '--update-baseline' in argv
    baseline_arg = None
    if '--baseline' in argv:
        try:
            baseline_arg = Path(argv[argv.index('--baseline') + 1]).resolve()
        except (IndexError, ValueError):
            print('CSS WIRING: BLOCKED — --baseline requires a path')
            return 2

    css_parts = []
    for rel in [
        'assets/css/style.css',
        'assets/css/responsive.css',
        'assets/css/admin.css',
        'assets/css/admin-responsive.css',
    ]:
        sheet = root / rel
        if sheet.is_file():
            css_parts.append(sheet.read_text(encoding='utf-8', errors='replace'))
    css = '\n'.join(css_parts)

    wanted = css_classes(css)
    have = markup_classes(root)
    orphans = sorted(c for c in wanted - have if c not in DYNAMIC_STATES)

    bpath = baseline_arg if baseline_arg is not None else root / BASELINE
    baseline = set()
    if bpath.is_file():
        baseline = {l.strip() for l in bpath.read_text().splitlines()
                    if l.strip() and not l.startswith('#')}

    new = [c for c in orphans if c not in baseline]
    fixed = sorted(baseline - set(orphans))

    if update:
        bpath.parent.mkdir(parents=True, exist_ok=True)
        bpath.write_text(
            '# CSS classes with no producer in templates or JS, tolerated as\n'
            '# LEGACY ONLY. Shrink this file when they are cleaned up; adding a\n'
            '# line to admit new CSS is the defect this gate exists to stop\n'
            '# (ledger R29 — r10 shipped dead review selectors for two rounds).\n'
            + '\n'.join(orphans) + '\n')
        print(f'baseline written: {len(orphans)} legacy orphan(s)')
        return 0

    for c in new:
        print(f'NEW ORPHAN  .{c} — styled in CSS, produced by no template or script')
    if fixed:
        print(f'note: {len(fixed)} baseline orphan(s) now wired or removed — shrink the baseline: {", ".join(fixed[:6])}')
    if new:
        print(f'\nCSS WIRING: FAIL — {len(new)} new orphan class(es). '
              'CSS for a new class ships in the SAME change as the markup that carries it.')
        return 1
    print(f'CSS WIRING: PASS — {len(wanted)} selector classes checked, '
          f'{len(orphans)} known legacy orphan(s), 0 new.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
