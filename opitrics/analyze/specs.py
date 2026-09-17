"""What the car actually is, beside what people say about it.

The comment analysis can tell you 340 people argue a kei car is too
heavy. It cannot tell you the kerb weight, so it cannot tell you whether
they are right — and a reader who arrives wanting the car rather than
the argument finds nothing here for them.

This module holds manufacturer figures to sit beside the themes. Three
rules make that safe rather than a dilution of the product:

**Every figure carries the page it came from, and one without a source
does not render.** That is the same rule `attach_sources` enforces on
quotes, applied to a different kind of claim. A page mixing sourced
comment figures with unsourced spec figures teaches a visitor that some
numbers here cannot be checked, and then none of them can be trusted.

**Nothing is computed, inferred or generated.** These are typed in from
a manufacturer page by a person. A model stating a kerb weight from
memory is the fabricated-quote failure in a new place, and there is no
corpus to check it against the way `check_quotes()` has one. If a figure
is not on a page someone can open, it does not go in the file.

**A spec states, it never judges.** "1,080 kg" is a fact about the car.
"Heavy for the class" is an opinion, and the only opinions this project
publishes belong to commenters with permalinks. The `note` field is for
context a manufacturer states — a measurement condition, a trim
caveat — not for a verdict.

The join to the analysis is `aspect`: the taxonomy key whose themes
discuss this figure. `drive.weight` specs appear beside the weight
argument, `ev.range` beside the charging complaints. That mapping is
what makes this discourse analysis with the facts attached rather than a
buying guide with sentiment bolted on.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Spec:
    """One manufacturer figure, with where it came from."""

    label: str
    value: str
    # The page this was read off. No source, no render — see module
    # docstring. Checked by `load`, not by the renderer, so a bad file
    # fails loudly at load rather than silently at publish.
    source_url: str
    source_name: str = ""
    # Taxonomy key whose themes discuss this figure, e.g. drive.weight.
    # Empty means the figure is real but nothing in the corpus raised
    # it — it still shows in the table, just with no comments attached.
    aspect: str = ""
    # A caveat the manufacturer states: measurement mode, trim, market.
    # Never a judgement.
    note: str = ""
    group: str = "Specification"


# The order spec groups appear in. Anything not listed sorts last, so
# adding a group to a subject file needs no code change.
GROUP_ORDER = [
    "Powertrain",
    "Battery & charging",
    "Body & dimensions",
    "Price",
    "Specification",
]


def load(path: Path) -> list[Spec]:
    """Read a subject's specs.json, dropping anything unsourced.

    A figure missing its source URL is logged and skipped rather than
    raising: one bad row should not cost the whole page, and the warning
    names the label so it can be fixed. But it never reaches a reader.
    """
    if not path.exists():
        return []

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        log.warning("specs.json is not valid JSON (%s) — no specs shown", exc)
        return []

    rows = raw.get("specs", raw) if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        log.warning("specs.json has no list of specs — no specs shown")
        return []

    out: list[Spec] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label", "")).strip()
        value = str(row.get("value", "")).strip()
        source = str(row.get("source_url", "")).strip()
        if not label or not value:
            continue
        if not source.startswith(("http://", "https://")):
            log.warning(
                "spec %r has no source URL — not published. Every figure "
                "needs a page a reader can open.", label,
            )
            continue
        out.append(
            Spec(
                label=label,
                value=value,
                source_url=source,
                source_name=str(row.get("source_name", "")).strip(),
                aspect=str(row.get("aspect", "")).strip(),
                note=str(row.get("note", "")).strip(),
                group=str(row.get("group", "")).strip() or "Specification",
            )
        )
    return out


def by_group(specs: list[Spec]) -> list[tuple[str, list[Spec]]]:
    """Specs grouped for display, in GROUP_ORDER then alphabetically."""
    groups: dict[str, list[Spec]] = {}
    for s in specs:
        groups.setdefault(s.group, []).append(s)

    def rank(name: str) -> tuple[int, str]:
        return (
            GROUP_ORDER.index(name) if name in GROUP_ORDER else len(GROUP_ORDER),
            name,
        )

    return sorted(groups.items(), key=lambda kv: rank(kv[0]))


# Minimum margin between a cluster's chosen aspect and its runner-up
# before that cluster may be shown as commentary on a spec.
#
# CLAUDE.md records that a confidence gate on aspect mapping was tried
# and rejected: it discarded 21% of the corpus and the mapped/rejected
# margins overlapped almost entirely. That finding stands, and this is
# not that gate — nothing here changes the analysis, the charts or the
# theme list. It governs one narrower claim.
#
# Pairing a spec with a theme asserts "the comment section said this
# about this figure", which is stronger than "this cluster is roughly
# about ride". At margin 0.006 the mapper was nearly indifferent
# between drive.ride and ev.general, and "Safety and fire risk fears"
# (margin 0.023, runner-up tech.safety) rendered under the suspension
# spec — implying 286 comments criticised the suspension when they were
# worrying about battery fires. That is the `defect` failure again: a
# figure borrowing a theme's weight for a complaint nobody made.
#
# A theme that does not clear this still appears in its own section with
# its own sentiment. It just is not cited as evidence about a spec.
MIN_PAIRING_MARGIN = 0.05


def themes_for(spec: Spec, clusters: list[dict]) -> list[dict]:
    """Themes that discuss this figure, largest first.

    Matches on the taxonomy key so the pairing is the one the analysis
    already made, not a keyword guess. Two exclusions:

    Meta clusters — a theme about the video's presenter is not
    commentary on kerb weight even when the mapper put it nearby.

    Clusters whose aspect was a near-tie. See MIN_PAIRING_MARGIN: the
    margin is how decisively this cluster belongs to this aspect rather
    than its runner-up, and a spec citation is too strong a claim to
    rest on a coin-flip.
    """
    if not spec.aspect:
        return []
    hits = [
        c
        for c in clusters
        if c.get("aspect") == spec.aspect
        and not c.get("is_meta")
        and c.get("margin", 0.0) >= MIN_PAIRING_MARGIN
    ]
    return sorted(hits, key=lambda c: -c.get("size", 0))


def coverage(specs: list[Spec], clusters: list[dict]) -> tuple[int, int]:
    """How many specs the corpus actually discussed, and the total.

    Worth printing: a subject where almost nothing is discussed is one
    where the spec table is decoration, and the `defect` failure was
    exactly a corpus with no product complaints being narrated as
    though it had them.
    """
    discussed = sum(1 for s in specs if themes_for(s, clusters))
    return discussed, len(specs)
