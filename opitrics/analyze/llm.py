"""LLM naming and narrative.

The only stage that leaves your machine, and it sends cluster summaries
— never raw comment dumps. About thirty short payloads per analysis,
which keeps this at fractions of a cent per run.

Every supported provider (DeepSeek, OpenRouter, Ollama) speaks the
OpenAI chat-completions dialect, so switching between them is a config
change rather than a code change.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from opitrics.config import LLMConfig

log = logging.getLogger(__name__)

NAMING_SYSTEM = """\
You analyse YouTube comment clusters about cars. Comments are often in \
Japanese, Chinese or English — read them in their original language.

For each cluster you receive representative comments and a statistical \
sentiment score. Return a short, concrete label describing what the \
cluster is actually about.

Rules:
- The label must be specific to the content, not generic. "Ground \
clearance worries" not "Negative feedback".
- Write labels in English, 2-6 words, no trailing punctuation.
- The `summary` is one sentence explaining what people are saying and why.
- If the cluster is not about the car (arguing between commenters, \
praising the reviewer, political fights), set `is_about_car` to false.
- `sarcasm_risk` is true when many comments read as sarcastic or ironic, \
because the statistical sentiment score will likely be wrong for those.
- Be accurate over charitable. If a cluster is hostile, say so plainly.

Some clusters arrive with `choose_from` — the embedding model could \
not separate its top candidates, so its `current_guess` is unreliable. \
Read the comments and pick the key from `choose_from` that actually \
fits, returning it as `aspect`. Keep the current guess only if it is \
genuinely right. Prefer the specific over the general: a cluster of \
nationalist argument is `brand.geopolitics`, not `meta.chatter`; \
accusations of paid promotion are `meta.sponsorship`, not `meta.chatter`. \
Return `aspect` as null only when nothing in the list fits — that marks \
a genuinely new topic and saying so is useful.

Return JSON only."""

NARRATIVE_SYSTEM = """\
You write analysis briefs for an automotive YouTuber preparing a video.

You receive named comment clusters with sizes and sentiment scores. \
Write a brief that tells them what the audience actually thinks and \
which angles are worth covering.

Rules:
- Lead with the most surprising or contentious finding, not a summary \
of the methodology.
- Cite specific numbers (cluster sizes, sentiment scores) — they matter \
for on-screen credibility.
- Flag where the data is weak or where sentiment scoring is unreliable.
- Distinguish clearly between opinions about the CAR and arguments \
about the brand's country of origin, the reviewer, or other commenters.
- No preamble, no "in conclusion". Write like a researcher briefing a \
colleague who is short on time.
- Plain prose with short paragraphs. Markdown headings are fine.

Return JSON only."""


@dataclass
class ClusterName:
    label: str
    summary: str
    is_about_car: bool
    sarcasm_risk: bool
    # Set when the LLM adjudicated an aspect the embedding mapper could
    # not separate. None means it saw the candidates and rejected them.
    aspect: str | None = None


def _naming_payload(cluster: dict, taxonomy: list[str] | None = None) -> dict:
    """One cluster, as the naming prompt sees it.

    A weakly-mapped cluster carries the full aspect vocabulary rather
    than the embedding model's shortlist. Offering only its top three
    runners-up assumes the right answer is somewhere in them — measured,
    it often is not: a cluster of nationalist argument was handed
    candidates that did not include `brand.geopolitics`, so the LLM
    picked the least-wrong of a bad set.
    """
    payload = {
        "id": cluster["cluster_id"],
        "size": cluster["size"],
        "sentiment": cluster["sentiment"]["label"],
        "polarity": cluster["sentiment"]["polarity"],
        "mapped_aspect": cluster.get("aspect_label"),
        "comments": [q["text"][:400] for q in cluster["quotes"][:6]],
    }
    # Offer candidates when the mapper abstained, or when it chose by a
    # hair — a margin under 0.02 means the runner-up was essentially
    # tied, and the LLM is better placed to break that tie.
    weak = cluster.get("margin", 1.0) < 0.02
    if not cluster.get("aspect") or weak:
        payload["current_guess"] = cluster.get("aspect")
        payload["choose_from"] = taxonomy or [
            k for k, _ in cluster.get("runners_up", [])[:3]
        ]
    return payload


class LLMClient:
    def __init__(self, config: LLMConfig, timeout: float = 120.0) -> None:
        self.config = config
        self.timeout = timeout
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
                timeout=self.timeout,
            )
        return self._client

    def _chat(self, system: str, user: str, max_tokens: int = 4000) -> dict:
        resp = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or "{}"
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Some providers wrap JSON in a fenced block despite the
            # response_format request.
            cleaned = content.strip().removeprefix("```json").removeprefix("```")
            cleaned = cleaned.removesuffix("```").strip()
            return json.loads(cleaned)

    def name_clusters(
        self,
        clusters: list[dict],
        batch_size: int = 8,
        taxonomy: list[str] | None = None,
    ) -> dict[int, ClusterName]:
        """Label clusters in batches.

        Batching keeps the request count low while giving the model
        enough context to distinguish neighbouring clusters from each
        other — naming them one at a time produces near-duplicate labels.
        """
        named: dict[int, ClusterName] = {}

        for start in range(0, len(clusters), batch_size):
            batch = clusters[start : start + batch_size]
            payload = {
                "clusters": [_naming_payload(c, taxonomy) for c in batch]
            }
            instruction = (
                "Label each cluster. Where `candidate_aspects` is present, "
                "also choose the aspect that fits, or null if none do. Return "
                '{"clusters":[{"id":<int>,"label":"...","summary":"...",'
                '"is_about_car":<bool>,"sarcasm_risk":<bool>,'
                '"aspect":"<key or null>"}]}\n\n'
                + json.dumps(payload, ensure_ascii=False)
            )

            log.info("naming clusters %d-%d…", start + 1, start + len(batch))
            try:
                result = self._chat(NAMING_SYSTEM, instruction)
            except Exception as exc:  # noqa: BLE001 - one bad batch must not lose the rest
                log.warning("naming batch failed: %s", exc)
                continue

            for item in result.get("clusters", []):
                try:
                    aspect = item.get("aspect")
                    named[int(item["id"])] = ClusterName(
                        label=str(item["label"]).strip(),
                        summary=str(item.get("summary", "")).strip(),
                        is_about_car=bool(item.get("is_about_car", True)),
                        sarcasm_risk=bool(item.get("sarcasm_risk", False)),
                        aspect=str(aspect) if aspect not in (None, "null", "") else None,
                    )
                except (KeyError, ValueError, TypeError):
                    continue

        return named

    def write_narrative(self, subject: str, summary: dict) -> dict:
        """Produce the written brief that sits at the top of the report."""
        instruction = (
            f"Subject: {subject}\n\n"
            "Write the brief. Return "
            '{"headline":"...","brief":"<markdown>","angles":["...","..."],'
            '"caveats":["...","..."]}\n\n'
            + json.dumps(summary, ensure_ascii=False)
        )
        log.info("writing narrative…")
        return self._chat(NARRATIVE_SYSTEM, instruction, max_tokens=6000)
