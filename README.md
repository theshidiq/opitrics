# Opitrics

*Opinion metrics.* Pronounced oh-PIT-rics.

Reads YouTube comment sections about cars and turns them into analysis
you can build content from — opinions in, measurements out.

```
discover → fetch → cluster → analyse → report → thread
```

Everything except the final naming and narrative runs locally on your
machine. Only ~30 cluster summaries ever leave it.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env      # then paste your keys in
.venv/bin/python scripts/doctor.py
```

Two keys are needed: a YouTube Data API key (free, 10,000 quota
units/day) and an LLM key — DeepSeek, OpenRouter, or nothing at all if
you point `LLM_PROVIDER` at a local Ollama. Embedding, clustering and
sentiment models download themselves on first run (~4GB) and cost
nothing.

## Running a subject

```bash
# what's hot right now
.venv/bin/python scripts/discover.py --top 10

# pull comments
.venv/bin/python scripts/fetch.py --subject byd-racco --query "BYD ラッコ" --region JP --limit 8

# clean → embed → dedupe → cluster
.venv/bin/python scripts/cluster.py --subject byd-racco

# aspect mapping + sentiment, all local
.venv/bin/python scripts/analyze.py --subject byd-racco --name "BYD Racco" --types kei ev

# LLM naming, charts, HTML report
.venv/bin/python scripts/report.py --subject byd-racco

# X thread with verified quotes
.venv/bin/python scripts/thread.py --subject byd-racco --name "BYD Racco"
```

Or drive the whole thing from the web UI:

```bash
.venv/bin/uvicorn opitrics.web.app:app --port 8420 --reload
```

## Layout

One directory per subject, so the fiftieth car does not make the output
folder unusable.

```
data/
  cache/opitrics.db              every comment ever fetched — never re-fetched
  output/
    discovery.json               last "what's hot" sweep
    subjects/
      byd-racco/
        subject.json             display name, vehicle types
        analysis/
          clusters.json          bottom-up themes
          analysis.json          aspects + sentiment — the source of truth
          narrative.json         LLM brief
        charts/
          aspects.png            dark, for video overlay
          aspects-light.png      light, for web and cards
          volume-intensity.png
          composition.png
        content/
          report.html            self-contained, charts embedded
          thread/
            thread.txt           copy, ready to paste
            thread.json
            01.png … 08.png      one card per post
        runs/
          2026-08-23T1412/       frozen copy of a previous analysis
```

Re-running `cluster.py` archives the previous `analysis/` and `charts/`
into `runs/<timestamp>/` before overwriting, so two analyses of the same
car stay comparable.

Old flat `subject__thing.json` files can be moved into this layout with:

```bash
.venv/bin/python scripts/migrate_layout.py --dry-run
```

## Things worth knowing

**The cache is the expensive part.** `data/cache/opitrics.db` holds every
comment ever fetched. Re-running any downstream stage costs zero quota.
Losing it means re-spending quota, so back it up.

**Clustering uses k-means, not HDBSCAN.** Comment embeddings form one
continuous cloud rather than dense islands; HDBSCAN either produced a
single 8,000-comment blob or discarded 90%+ as noise at every setting
tried. `--method hdbscan` is still there if a corpus suits it.

**Aspect mapping uses embedding similarity, not zero-shot NLI.**
Cross-lingual NLI put rural-charging comments into "brand trust" at 0.96
confidence. Embeddings against short bilingual descriptions handled the
same cases correctly. `ZEROSHOT_MODEL` in `.env` is unused.

**Sarcasm detection is weak**, especially in Japanese. Clusters where the
LLM flags `sarcasm_risk` should not have their polarity quoted as fact.

**Every quote on a card is verified verbatim** against the corpus before
rendering. A paraphrased quote would put invented words in a real
person's mouth on a public timeline.

**Translations are checked before publishing.** `scripts/check_translations.py`
re-translates every quoted comment independently and reports where the two
readings disagree. It found 6 disagreements in 20 on the first Racco threads,
one of them material — a card that dropped a closing rhetorical question and
changed what the commenter meant. Run it before posting:

```bash
.venv/bin/python scripts/check_translations.py --subject byd-racco
```

Running it with the same model that wrote the translations catches slips but
not systematic blind spots. Point `LLM_PROVIDER` at a different model for a
genuinely independent read.

**Commenters are not buyers.** This measures perception, not purchase
intent. Say so on camera.
