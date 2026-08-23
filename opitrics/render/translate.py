"""Check translations before they are attributed to anyone.

A quote card carries a real person's words and a permalink proving they
said something. If the translation beside it is wrong, the permalink
becomes evidence against you rather than for you — the reader can see
the original and see that your English does not match.

The pipeline cannot read Japanese, so it cannot mark its own homework.
What it can do is translate a second time, independently, and refuse to
publish where the two readings disagree about meaning. Disagreements go
to a human; they are not resolved automatically.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from opitrics.analyze.llm import LLMClient

log = logging.getLogger(__name__)

CHECK_SYSTEM = """\
You verify translations of YouTube comments about cars, from Japanese or \
Chinese into English.

You receive the original comment and a proposed English translation. \
Translate the original yourself, independently, then judge whether the \
proposed translation conveys the same meaning.

Return for each item:
- `independent` — your own translation, natural English, not a gloss.
- `verdict` — one of:
    "ok"       the proposed translation is accurate.
    "nuance"   accurate in substance but loses tone, register or hedging \
(sarcasm read as sincere, a question read as a statement, casual speech \
read as formal).
    "wrong"    says something the original does not say, or omits \
something that changes what the commenter meant.
- `note` — one sentence, only when the verdict is not "ok", naming the \
specific difference.

Judge meaning, not wording. Two good translations of the same sentence \
will differ; that is not an error. Mark "wrong" only when a reader of \
the English would come away believing something the commenter did not \
say.

Be particularly careful with:
- Japanese sentence-final particles and hedges (かなあ, でしょう, けど) \
which soften or question a statement that looks flat in English.
- Sarcasm carried by politeness or emoji rather than by word choice.
- Dropped subjects, where English must supply a "they" or "I" that the \
Japanese leaves open — check the proposed translation picked the right one.

Return JSON only."""


@dataclass
class TranslationCheck:
    original: str
    proposed: str
    independent: str
    verdict: str
    note: str

    @property
    def ok(self) -> bool:
        return self.verdict == "ok"

    @property
    def blocking(self) -> bool:
        """Whether this should stop a card being rendered.

        "nuance" does not block: it is a judgement call the author can
        make with the note in front of them. "wrong" does.
        """
        return self.verdict == "wrong"


def check_translations(
    client: LLMClient,
    pairs: list[tuple[str, str]],
    batch_size: int = 6,
) -> list[TranslationCheck]:
    """Verify (original, proposed) pairs with an independent translation.

    Batched small: this is the one stage where being wrong is publicly
    embarrassing, so it gets more room per item than the naming pass.
    """
    out: list[TranslationCheck] = []

    for start in range(0, len(pairs), batch_size):
        batch = pairs[start : start + batch_size]
        payload = {
            "items": [
                {"id": i, "original": original[:600], "proposed": proposed[:600]}
                for i, (original, proposed) in enumerate(batch)
            ]
        }
        instruction = (
            "Verify each translation. Return "
            '{"items":[{"id":<int>,"independent":"...",'
            '"verdict":"ok|nuance|wrong","note":"..."}]}\n\n'
            + json.dumps(payload, ensure_ascii=False)
        )

        log.info("checking translations %d-%d…", start + 1, start + len(batch))
        try:
            result = client._chat(CHECK_SYSTEM, instruction, max_tokens=4000)
        except Exception as exc:  # noqa: BLE001 - an unchecked pair is reported as such
            log.warning("translation check failed: %s", exc)
            for original, proposed in batch:
                out.append(
                    TranslationCheck(
                        original=original,
                        proposed=proposed,
                        independent="",
                        verdict="unchecked",
                        note=f"check failed: {exc}",
                    )
                )
            continue

        by_id = {}
        for item in result.get("items", []):
            try:
                by_id[int(item["id"])] = item
            except (KeyError, ValueError, TypeError):
                continue

        for i, (original, proposed) in enumerate(batch):
            item = by_id.get(i)
            if not item:
                out.append(
                    TranslationCheck(
                        original=original,
                        proposed=proposed,
                        independent="",
                        verdict="unchecked",
                        note="no verdict returned",
                    )
                )
                continue
            verdict = str(item.get("verdict", "unchecked")).lower()
            if verdict not in {"ok", "nuance", "wrong"}:
                verdict = "unchecked"
            out.append(
                TranslationCheck(
                    original=original,
                    proposed=proposed,
                    independent=str(item.get("independent", "")).strip(),
                    verdict=verdict,
                    note=str(item.get("note", "")).strip(),
                )
            )

    return out
