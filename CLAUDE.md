# Opitrics

**Opinion metrics** — oh-PIT-rics. The name is a contraction, and it
describes the job: opinions in, measurements out.

Say the derivation wherever there is room for a line of text. It does
not work as a standalone bio, though — "opinion metrics" reads as
market research, market research implies buyers, and commenters are not
buyers. It is an etymology beside the name, never the explanation on
its own. `brand/PROFILE.md` carries the full reasoning and the per-
platform wording.

A YouTube comment-analysis machine for automotive content. It fetches a
car's comment sections across languages, clusters them, scores
sentiment, maps themes onto an aspect taxonomy, and produces X threads
and vertical shorts from the result.

Every published claim traces back to a real comment with a permalink.
That is the product. A viewer who checks one number and finds it wrong
costs more than the view was worth.

## Division of labour

**This file is the pipeline.** Fetching, clustering, sentiment,
rendering, publishing plumbing.

**Social media is the main assistant's.** Account management, posting
cadence, what ships and when, pre-publication checks, and the profile
layer in `brand/`. Consult the `social-strategist` agent
(`.claude/agents/social-strategist.md`) for editorial judgment —
angles, hooks, narration voice, titles, platform fit — and decide with
it rather than handing the whole task over. When the question is "what
should this short say", that is a consultation; when it is "should
this go out today", that is yours.

**The public web presence belongs to the `web-steward` agent**
(`.claude/agents/web-steward.md`): the sources audit pages, GitHub
Pages, `opitrics.com` and its DNS, Workspace email. Anything a visitor
loads in a browser that is not a video or a post.

Nobody publishes without the user saying so for that specific item.
That applies to all three.

## Running it

Order matters; each stage reads the previous one's output.

```bash
.venv/bin/python scripts/doctor.py                          # config + hardware check
.venv/bin/python scripts/discover.py                        # find cars having a moment
.venv/bin/python scripts/fetch.py    --subject byd-racco    # → SQLite cache
.venv/bin/python scripts/cluster.py  --subject byd-racco    # clean, embed, dedupe, k-means
.venv/bin/python scripts/analyze.py  --subject byd-racco    # sentiment + aspect mapping
.venv/bin/python scripts/report.py   --subject byd-racco    # LLM names themes → analysis.json
.venv/bin/python scripts/thread.py   --subject byd-racco    # X thread
.venv/bin/python scripts/shorts.py   --subject byd-racco --all   # five vertical shorts
.venv/bin/python scripts/sources.py  --subject byd-racco    # audit page
```

`fetch` is the only stage that spends YouTube quota (10,000 units/day;
search costs 100). Everything downstream reads the SQLite cache, so
re-running analysis is free. Never add a fetch to a stage that could
read the cache instead.

`scripts/short.py` and `scripts/datashort.py` are superseded by
`scripts/shorts.py`. Don't extend them.

## Decisions already made, with the evidence

Each of these was tried the other way first. Reopen them only with new
measurements, not intuition.

**k-means, not HDBSCAN.** Every parameter setting gave either one
8,000-comment blob or 90%+ noise. Comment embeddings form a continuous
cloud, not dense islands. `cluster_hdbscan` still exists; it is not the
default for this reason.

**Embedding similarity for aspect mapping, not zero-shot NLI.** The NLI
model mapped rural-charging complaints to "brand trust" at 0.96
confidence and produced "brand trust" fifteen times across distinct
clusters.

**No margin gate on aspect mapping.** A confidence gate discarded 21% of
the corpus; mapped and rejected margins overlapped almost entirely
(0.016–0.170 vs 0.001–0.029). A relative margin made it worse. The LLM
adjudicates with the full taxonomy instead.

**Remotion, not movis, for shorts.** Real per-frame rendering. The movis
path faked bar growth with seven cross-faded PNGs and the steps were
visible. movis also leaked ~1GB of diskcache per render — 35 orphans
filled a disk twice — hence `_sweep_caches()`.

**Raw comments never leave the machine.** Only ~30 cluster summaries go
to the LLM for theme naming. Keep it that way.

## Traps that have already bitten

- **`strip_emoji` and CJK.** A regex range `\U000024C2-\U0001F251`
  spans CJK and silently deleted all Japanese. Use narrow explicit
  ranges, and check the font cmap before shipping a glyph.
- **Fonts per script.** Hiragino Sans lacks simplified Chinese forms
  (renders tofu) — `Hiragino Sans GB` handles those. Latin needs
  Helvetica Neue; leaving it to Hiragino collides.
- **`staticFile()` in Remotion.** A bare `<img src="img-01.jpg">`
  404s silently and renders white. Use `<Img src={staticFile(src)}>`.
- **Wikimedia suffixes.** `Path(url).suffix` returns query-string tail.
  Use `Path(image.title).suffix`.
- **Voice cache keys.** `speak()` caches by voice+model+settings+
  neighbours+text. Post-processing (`deepen`) is applied to the output
  copy, never the cache, or rebuilds compound the effect.
- **ElevenLabs `stability` is inverted.** High = flatter. Values above
  the voice's own recommended default produce monotone narration.

## Verifying rendered output

Reading the code is not enough — every backdrop and typography bug in
this repo was found by looking at frames, not by reasoning.

```bash
ffmpeg -y -v error -ss 7 -i short.mp4 -frames:v 1 -vf "scale=304:-2" /tmp/f.png
```

Then `Read` the PNG. For a contact sheet across angles, extract one
frame each and `hstack`. Check contrast against the *encoded* video
rather than CSS values — H.264 is what the viewer sees.

## Safety rails — do not remove

- **`.env` is git-ignored and has never been committed.** Verify before
  every push. Keys must never appear in the transcript; if one does, it
  needs rotating.
- **`check_quotes()` in `scripts/shorts.py`** blocks narration that
  attributes invented words to real commenters. This is not
  belt-and-braces — the model has already produced fluent, entirely
  fabricated quotes that reached rendered video. A missing short beats
  a fake quote. Never route around this gate.
- **Usernames are withheld** from every card. The permalink is what
  makes a quote checkable.
- **Japanese-language output may only quote comments originally written
  in Japanese.** `check_quotes()` works because its corpus is
  `q["text"] + q["english"]` — every string that can legitimately reach
  a card is in one of those two fields. A Japanese rendering of an
  English comment is in neither, so it either fails the gate or, worse,
  someone adds a `q["japanese"]` field to make it pass — at which point
  the gate validates a translation nothing ever checked and reports
  success. `translate.py` verifies one direction only, into English;
  there is no outbound check and building one is a project, not a
  patch. Cross-language findings in Japanese content are stated as
  counts, never as quotes: an aggregate crosses the language boundary
  safely, attributed words never do.
- **Publishing stops for human review.** `scripts/publish.py` previews
  in a browser; `scripts/upload.py` defaults to private. Never post,
  upload, or make public without the user saying so for that specific
  item.

## Two repos, deliberately split

- `theshidiq/opitrics` — **private**. Pipeline, prompts, method.
- `theshidiq/opitrics-sources` — **public**. Audit pages only: the
  evidence, not the method.

Never push pipeline code to the public repo.
