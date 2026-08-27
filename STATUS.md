# Status

Shared board for the three roles working on Opitrics — the main
assistant (social), `web-steward` (public web), and whoever is in the
pipeline. Anyone may edit; keep it current or delete the stale line.

`CLAUDE.md`, `brand/PROFILE.md` and the agent briefs are the durable
record of *decisions*. This file is the record of *state* — what is
done, what is blocked, and on whom. If something here stops being
state and becomes a decision, move it there and drop it from here.

Last updated 2026-08-27 (first thread live on X; disk state audited
against what was actually published).

## Accounts

| Platform  | Handle           | Account | Credentials | Can publish |
|-----------|------------------|---------|-------------|-------------|
| X         | `opitrics`       | held    | **verified** | **yes — posting** |
| TikTok    | `opitrics`       | held    | **verified** | **yes** |
| Instagram | `opinionmetrics` | held    | **verified** | blocked — see below |
| YouTube   | `opitrics`       | not claimed | — | blocked — see below |

**First publication: the `quotes` thread, X, 2026-08-26.**
`x.com/opitrics/status/2092531936271245540` — 10 posts, one card each,
receipt complete with no errors. Nothing has been posted anywhere else.

**The live thread is not the one on disk.** `quotes/thread.json` was
regenerated after publishing, and the two share no posts — 0 of 10
identical. Anything measured against the current files describes a
draft, not what the public sees. `posted.json` stores the text of every
post that actually went out; that is the only record of the live thread,
since the app cannot read from X.

Audited against the receipt rather than the disk: **no rounded counts,
no corpus superlatives, quotes verified before posting.** What is live
is accurate. It is written in the older voice — four posts open with an
award-ceremony phrase ("A voice of reason:", "The funniest jab:",
"Skeptics smell astroturfing:") that `STORY_SYSTEM` now forbids, and it
carries 11 em dashes. A style gap, not a correction-worthy one. Do not
delete and repost over voice; the archive is more valuable intact.

Three things that only the first live post could settle:

- **Write scope works.** `verify_credentials` is a read call and passes
  on a read-only token, so nothing before this proved the app could
  actually post.
- **X credits are prepaid, not billed in arrears.** "Pay as you go"
  reads as the latter; a zero balance returns `402 credits depleted`.
  It failed on the first call, so nothing partial reached the timeline
  — but a mid-thread exhaustion would leave half a thread published,
  so keep a balance ahead of a run rather than topping up on failure.
- **The app cannot read.** Free tier is write-only: `get_tweets` on the
  posts it just made returns 401. Verification is the receipt in
  `content/threads/<angle>/posted.json`, or opening the URL. Do not
  build anything that reads back from X.

**On signing up with aliases.** An alias is an address, not an account —
it has no password and cannot be signed into, so "Sign in with Google"
rejects it ("account not found"). Either sign up with email + password
to use a per-platform alias, or use Sign in with Google and accept that
the platform gets the real account address. Not both. YouTube is the
exception either way: a channel belongs to an account, so it must be
Sign in with Google as the Workspace user.

**Instagram is blocked on hosting, not credentials.** Meta does not
accept a file upload — it is handed a public URL and fetches the video
itself (`opitrics/publish/meta.py`, top of file). The shorts are local
files and nothing serves them publicly. This is the one cross-role
question outstanding: **web-steward, is there a place to serve a
rendered MP4 from, publicly, for the minutes Meta needs to fetch it?**
It does not need to be permanent or discoverable.

**YouTube is blocked on a Google restriction that lifts by itself.**
New Workspace accounts cannot use YouTube — no uploads, no channel
creation — until 30 days from account creation, or $30 in processed
charges. Expected to clear around late September 2026; check the actual
Workspace creation date rather than counting from today. When it
unlocks, create the channel as a **Brand Account** — that keeps the
channel separate from the login so managers can be added or ownership
transferred later. It cannot be changed after creation.

## Verified, so nobody re-derives it

**Instagram / Meta.** All five keys in `.env`. Confirmed live: the
account resolves as `opinionmetrics`, and `content_publishing_limit`
returns 0 of 100 per 24h — note `meta.py` assumes 25. App Review is
**not** needed: Meta's docs are explicit that Standard Access covers
apps serving accounts you own, so `dev_mode` plus the Instagram Tester
role is the correct end state, not a temporary one.

Two things that cost an hour and would cost the next person the same.
The Page is owned by a **business portfolio**, so `me/accounts` returns
an empty array and `me/businesses` fails with "(#100) An owning
business is required for this request" — the IDs come from Business
Settings at `business.facebook.com` instead, or by querying the Page
node directly once its ID is known. **`meta.py` may hit the same wall**
if it derives a Page token via `me/accounts`; unverified, and worth
checking before the first real publish. Also: Instagram's *web*
settings cannot link a Facebook Page at all — that has to be done from
the Facebook side.

**TikTok.** All four keys in `.env`. `creator_info` resolves: username
`opitrics`, nickname "Opinion Metrics", max duration 600s.

Two findings that contradict what `opitrics/publish/tiktok.py`
documents, both worth knowing before trusting either:

- `privacy_level_options` includes `PUBLIC_TO_EVERYONE`. The module's
  docstring says unaudited clients are forced to `SELF_ONLY`. Do not
  assume either is right — the docstring also warns that the failure
  mode is an upload that "succeeds" while silently being private. The
  first real post settles it.
- **`push_by_file` needs no domain verification**; only `pull_by_url`
  does. So TikTok takes the file directly and has no hosting
  dependency, unlike Meta.

TikTok's production audit requires a demo video of a real posting
**interface** on `opitrics.com` — login, creator info, privacy
selector, publish. No such interface exists, and building one purely to
pass review was judged not worth it yet. Sandbox is configured, which
validates the code path but never actually publishes. Post manually
until the numbers justify the build.

**The Meta developer MCP** (`meta_developer_tools`) works, but its
tools are reachable from the **terminal CLI only** — the OAuth token
lives in that CLI's credential store and the desktop app neither reads
it nor has a `/mcp` command to run the flow. Not stale state, not a
dropped connection. Everything it reports is visible in the Meta
dashboard anyway.

## Closed

**The sources URL.** `deploy_sources.py` has `DOMAIN = "opitrics.com"`,
the index is live and links `byd-racco/`, and `/terms` and `/privacy`
are up. This was the one hard deadline — descriptions embed the URL
permanently — and it is settled before the first upload rather than
after. Thanks, web-steward.

**Apex, not subdomain.** `opitrics.com` at the root, four A records to
GitHub's IPs on Cloudflare DNS. **Proxy must stay off** (grey cloud):
proxied, GitHub cannot validate the domain and never issues the
certificate, so the page whose job is looking trustworthy would greet a
skeptic with a browser security warning. Verified: HTTPS enforced, cert
clean, HTTP 301s to HTTPS.

Nothing published carried the old `github.io` path when it moved — the
only thread on disk was a dry run (`tweet_id: dry-1`) — so no redirect
debt was taken on. GitHub also auto-redirects the old repo path. The
apex is now permanent per the link-permanence rule.

**The palette mismatch is fixed.** Audit pages, index, terms, privacy
and the charts all mirror `remotion/src/theme.ts`. Carried its measured
ratios rather than re-picking by eye; the old `#807B6E` ran near 3.5:1
on 10.5px labels, the same failure `theme.ts` records for `#909090`.
Every text role now measures at least 6.9:1.

Charts needed a third palette — `DARK` is video overlay, `LIGHT` is the
internal web UI, and neither is what the account publishes. `WEB` in
`charts.py` is the published one.

**The report is public.** `opitrics.com/byd-racco/` is now the full
analysis — composition split, aspect-sentiment chart, all 32 themes
with their positive/neutral/negative bars, volume-intensity scatter.
The audit page moved to `byd-racco/sources.html` and the old URL still
resolves as the index. Every theme carries a comment with a permalink;
a quote with no source is not rendered at all.

**The threads described the wrong page, and now don't.** All five
closing posts promised "the full video list is published" at
`opitrics.com/byd-racco/` — which serves the *report*. The video list
is one click further on, at `sources.html`. The wording came from the
prompt in `story.py`, written when that URL was the audit page, and it
did not follow when the report took over the path.

Small, but it sat under "check the data yourself", which is the one
claim that has to survive being checked. The prompt now tells the model
to describe what is actually at the URL and explicitly not to promise a
video list or a quote list. Rebuilt: five threads, longest post 279 of
280, 27 quotes verbatim against the corpus, 23/23 translations clean.

**Email.** Workspace Starter on the domain, MX live. One seat, aliases
per platform. `info@opitrics.com` is on five public pages as the route
for both corrections and takedown requests, and **confirmed receiving**
(2026-08-26).

There is no Google Workspace **Admin SDK** connector available in this
session and none in the MCP registry, so aliases, domain verification
and mail routing are console work, not automatable from here. A
service-account client was considered and rejected: it needs a
domain-wide-delegation key on disk to save a handful of one-time
clicks.

## Possible, not planned: selling the analysis

Raised 2026-08-26. Nobody has approached us and there is no product, no
pricing and no named buyer. It is recorded because one live constraint
protects it and could otherwise be relaxed by someone who does not know
why it exists.

**Never imply sales, demand or market outcome. Not once, anywhere.**
That rule is already in `CLAUDE.md`, in the bio, and as rule 4 in the
`social-strategist` brief, where it exists to stop a bad reply. It now
has a second job: if a brand ever does approach, "we never claimed
demand signal" has to be true across the whole archive, retroactively.
Every post is evidence in that conversation. A single loose line costs
more later than it gains now.

What is genuinely sellable is **discourse analysis, not market
research** — what the conversation about a car contains, with every
claim traceable to a permalink. Nobody else does that verifiably; the
comparable tools are keyword counts. What is NOT sellable is anything
about buyers, and "business decision analysis" is the phrase that
implies otherwise. A client who acts on comment sentiment as demand and
is wrong is a refund plus a reputation, which is a far worse failure
than a wrong reply.

Two things this does not require deciding yet. The buyer is unknown —
OEM comms, agencies and automotive media want different artefacts, so
let the public account surface who actually turns up rather than
guessing. And the pipeline is subject-agnostic: only the aspect
taxonomy is car-specific, so going beyond cars is a taxonomy swap
rather than a rebuild. Nothing is painted into a corner.

One consequence for what ships: the `method` thread is the portfolio
piece. A prospective buyer reads that one hardest, because it is the
one that says whether the numbers are real.

## Open, by owner

**web-steward** — the public MP4 question above is the only one left;
palette and apex are both closed. **Provisional answer: yes, and it is
cheap.** The sources repo is public and already served over HTTPS from
`opitrics.com`, so an MP4 committed under a path there is a public URL
Meta can fetch. Two caveats before anyone relies on it: GitHub asks that
Pages not be used as a CDN, and a 1080×1920 short is a few MB per file
committed permanently to git history — so upload, publish, then delete
the file in a follow-up commit rather than accumulating them. If that
proves unacceptable, the fallback is a signed URL from any object store;
it needs to live for minutes, not forever. Not built — say the word.

**Pipeline** — the Japanese output path, if and when the Japanese arm
starts. `brand/PROFILE.md` lists what must be true first; the headline
item is that `remotion/src/theme.ts` has no simplified-CJK face and
falls through to Hiragino Sans, which `CLAUDE.md` records as rendering
tofu. Latent while CJK lives in matplotlib quote cards, certain once
every card is Japanese.

### Thread voice: handing this to the pipeline

Prompt-level fixes have stopped converging and this needs a code
change, not another regeneration. I ran five rounds of prompt edits and
got the em dash count from 39 to a floor it will not go below, which is
the signal that the remaining instances need a deterministic gate the
way `check_rounding()` and `check_sources_post()` already do. Those two
work; the taste rules only mostly work.

**What is actually true right now**, measured rather than assumed:

- **Images are fixed.** 39 cards, 39 unique content hashes, zero
  identical, no chart reused across threads. `charts_taken` and
  `quotes_taken` thread through `extract_story` and are mutated in
  place. If a duplicate is still visible, it is a stale file from an
  earlier run, not the current build — check the timestamp before
  re-fixing this.
- **Dashes: 19 total, 14 separator, 5 prose** as measured 2026-08-27
  after the latest rebuild — not the 8/5/3 recorded earlier, which was
  a different build. The prose five are `defenders/4`, `defenders/6`,
  `method/4`, `quotes/1`, `quotes/3`.

  Two of those are an artefact worth knowing about before writing the
  gate. `method/4` and `quotes/3` read as `「」 — NN likes` once the
  quote is stripped: removing the quote text orphans its separator, and
  a naive counter then reads the orphan as prose. So the trap runs both
  ways — the earlier undercount stripped too little, this one strips too
  much. **Strip the separator by pattern (`—\\s*[\\d,]+\\s*likes`), not
  by what precedes it.**

  `quotes/3` is the one to look at first regardless of dashes: "isn't
  ride quality — it's the 1.2t weight" is the not-but tail the prompt
  explicitly forbids, so at least one prose dash is a symptom rather
  than the disease.

**What I suggest, in priority order:**

1. **A `check_dashes()` gate**, mirroring `check_rounding()`. Strip the
   quote and its translation from the post text first, then strip the
   `— NN likes` separator, then count. More than one prose dash per
   thread fails the build. This is the fix; everything else is
   secondary.
2. **Consider stripping prose dashes post-hoc** rather than gating.
   Most are `X, and Y` or `X. Y` with the dash doing no work. A
   deterministic rewrite is cheaper than another prompt round and
   cannot regress. Gate what cannot be rewritten safely.
3. **Do not add more prompt rules.** `STORY_SYSTEM` is now ~7,600
   characters and the last three additions bought less than the first
   one did. Rules are competing with each other for the model's
   attention.

**The lesson worth keeping from this, because it cost five rounds.**
The `method` thread wrote "16,000 comments" six times for a corpus of
15,950 while an explicit anti-rounding rule sat in the prompt. I
treated that as the model ignoring instructions. It was not — the
`method` angle's own brief said *"Explain how 16,000 comments become a
finding"*, and the model was faithfully copying it. Two other places
planted the same number, including the rule forbidding it.

**Never put an illustrative figure in a brief or an example.** A
hardcoded number outranks a rule about numbers every time. Worth
grepping the other prompts for the same trap before it costs someone
else the same afternoon.

**Social (main assistant)** — the `quotes` thread is live on X, so the
open questions are now the four remaining threads and how far apart
they go, plus which of the five shorts leads and where. X is proven
end to end; TikTok can publish today.

Editorial decisions made, not yet acted on:

- **`numbers` leads the shorts, then `quotes`, every other day.** Not
  because `numbers` is the best video — `quotes` is more watchable —
  but because a first post establishes what the account is. Lead with
  the argument videos and the founding document is
  car-nationalism content; lead with `numbers` and it is "we count
  things and show our work", which can host the others later. Every
  other day rather than daily: four videos is the whole inventory for
  this subject, and a 48-hour gap lets the first video's retention
  inform the second's hook.
- **`defect` does not ship.** It narrates "Range expectations dominate
  the chatter" for a cluster ranking **39th of 40 at n=239**, and says
  the loudest complaint is range when the badge argument is rank 1 at
  681. Rules 3 and 6 in one beat, and the closing card sends viewers to
  a page that ranks every theme by count, where range sits at the
  bottom. Needs a re-scope in `angles.py` — but **not onto "Underbody
  quality criticism"**, suggested earlier and since checked: it is
  `sarcasm_risk: True`, so it walks straight into the rule 5 problem
  that is holding `defenders`. "Battery ground clearance risk" (359,
  rank 20, −0.504, unflagged) is the clean one.
- **`defenders` holds** until beats 2 and 3 are re-cut. They quote the
  `sarcasm_risk: True` "Encouraging purchase" cluster and narrate it as
  sincere support with a motive nobody expressed. Rule 5. Clean
  substitute: "Hope for domestic competition" (317, +0.440, unflagged).

That last one is worth carrying beyond this subject: **`check_quotes()`
passed `defenders` because the quoted words are real. What was invented
is the sentence around the quote.** The gate verifies quotes; nothing
verifies narration about a quote.

**The X profile is filled in** (2026-08-26) — bio, avatar, header,
display name. A visitor arriving from the live thread now lands on a
finished profile rather than an empty one.

An X-shaped header exists at `brand/out/header-x-1500x500.png`. X's
header is 3:1 where YouTube's visible strip is 6:1, so the older
`banner-crop-*` files letterbox or clip the wordmark there. Both come
from the same master; the text block is centred precisely so one render
survives both ratios.

The two blocked shorts are listed under Social above. Two details that
belong with them and are not repeated there: `defect`'s beat 2 inverts
the finding outright — it says the loudest complaint is range when the
badge argument is rank 1 at 681 — and `defenders` narrates
「そこまで惚れたなら買えば良いじゃん!」, which is needling the reviewer,
as "He's not even a buyer. He just wants to see it happen". A motive
nobody expressed, attached to a sarcasm-flagged cluster.

Worth recording as a gap rather than a bug: `check_quotes()` passed
`defenders` because the quoted words are real. What is fabricated is the
sentence *around* the quote. **The gate verifies quotes; nothing
verifies the narration about a quote.**

One that is nobody's yet, now narrowed. The promise itself **is** on
screen: every short closes on a card reading "every quote links to the
original comment" under a `check the work` eyebrow — verified by
pulling the final frame, not by reading the source.

What is missing is the destination. `--sources-url` reaches the
narration, so the address is spoken and written into the description,
but no card renders it as text. Vertical video is watched muted by
default, so a muted viewer gets the claim and no way to act on it.
Still a render-layer change and still a content problem; the gap is
just smaller and more specific than it was.

`info@opitrics.com` receives — confirmed by the user 2026-08-26. The
corrections and takedown route on both public pages is live, so the
"if a number is wrong I want to know" promise in `brand/PROFILE.md`
is one somebody can actually act on.
