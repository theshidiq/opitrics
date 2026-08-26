# Status

Shared board for the three roles working on Opitrics — the main
assistant (social), `web-steward` (public web), and whoever is in the
pipeline. Anyone may edit; keep it current or delete the stale line.

`CLAUDE.md`, `brand/PROFILE.md` and the agent briefs are the durable
record of *decisions*. This file is the record of *state* — what is
done, what is blocked, and on whom. If something here stops being
state and becomes a decision, move it there and drop it from here.

Last updated 2026-08-26.

## Accounts

| Platform  | Handle           | Account | Credentials | Can publish |
|-----------|------------------|---------|-------------|-------------|
| X         | `opitrics`       | held    | in `.env`, untested | unknown |
| TikTok    | `opitrics`       | held    | **verified** | **yes** |
| Instagram | `opinionmetrics` | held    | **verified** | blocked — see below |
| YouTube   | `opitrics`       | not claimed | — | blocked — see below |

Nothing has been posted anywhere. No bios or assets pasted in yet;
`brand/PROFILE.md` has all of it ready.

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

## Open, by owner

**web-steward** — the public MP4 question above. Also still on your
list from your own brief: the palette mismatch between the audit pages
and the video/account identity, and apex vs subdomain if that is not
already decided by the live setup.

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
