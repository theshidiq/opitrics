# Status

Shared board for the three roles working on Opitrics — the main
assistant (social), `web-steward` (public web), and whoever is in the
pipeline. Anyone may edit; keep it current or delete the stale line.

`CLAUDE.md`, `brand/PROFILE.md` and the agent briefs are the durable
record of *decisions*. This file is the record of *state* — what is
done, what is blocked, and on whom. If something here stops being
state and becomes a decision, move it there and drop it from here.

Last updated 2026-08-26 (web presence: domain live, report published).

## Accounts

| Platform  | Handle           | Account | Credentials | Can publish |
|-----------|------------------|---------|-------------|-------------|
| X         | `opitrics`       | held    | in `.env`, untested | unknown |
| TikTok    | `opitrics`       | held    | **verified** | **yes** |
| Instagram | `opinionmetrics` | held    | **verified** | blocked — see below |
| YouTube   | `opitrics`       | not claimed | — | blocked — see below |

Nothing has been posted anywhere. No bios or assets pasted in yet;
`brand/PROFILE.md` has all of it ready.

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

**Email.** Workspace Starter on the domain, MX live. One seat, aliases
per platform. `info@opitrics.com` is on five public pages as the route
for both corrections and takedown requests — **it has not been
confirmed to receive; send it a test.** A bouncing corrections address
on a page arguing its numbers survive checking is worse than none.

There is no Google Workspace **Admin SDK** connector available in this
session and none in the MCP registry, so aliases, domain verification
and mail routing are console work, not automatable from here. A
service-account client was considered and rejected: it needs a
domain-wide-delegation key on disk to save a handful of one-time
clicks.

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

**Social (main assistant)** — which of the five rendered shorts goes
first, how the rest are sequenced, and the launch post. Not blocked by
anything above; TikTok can publish today and X is untested but
probably fine.

One that is nobody's yet: the bios promise every number links to its
source, but on the shorts that promise appears only in the description
and the audit pages. A viewer who never taps through sees the watermark
and nothing else — and that promise is the whole differentiator. It is
a render-layer change, so pipeline work, but it is a content problem.
Worth someone owning.

What changed under it: the destination is now a readable report rather
than a wall of quotes, so tapping through is worth more than it was.
The promise is still invisible until they tap, which is the actual
problem and is untouched.

Threads on disk already carry `https://opitrics.com/byd-racco/`, so
they are consistent with the live site. Note that URL is now the
**report**, not the audit page — which is the better landing page for a
thread link, but if any card's wording promises a raw quote list, it
points somewhere slightly different from what it says. Worth a read
before the first post.
