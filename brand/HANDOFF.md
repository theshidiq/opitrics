# Handoff — social, 2026-08-26

**Delete this file once you have read it and the open items below are
resolved or recorded somewhere permanent.** It exists because a session
ended mid-setup, not because it is reference material. `CLAUDE.md`,
`brand/PROFILE.md` and the two agent briefs are the durable record;
anything here that outlives the setup should move into one of those
first.

## Where the accounts actually are

| Platform  | Handle           | State |
|-----------|------------------|-------|
| X         | `opitrics`       | registered |
| TikTok    | `opitrics`       | registered |
| Instagram | `opinionmetrics` | registered — `opitrics` was taken |
| YouTube   | `opitrics`       | **not claimed.** Free as of 2026-08-26 |

Nothing has been posted anywhere. No bios or assets pasted in yet —
`brand/PROFILE.md` has all of it ready.

**YouTube is blocked until roughly late September 2026.** Google bars
new Workspace accounts from YouTube — no uploads, no channel creation —
until one of: $30 processed in charges, 30 days of account age, or
purchase through a reseller. The 30 days runs from Workspace account
creation, not from domain verification, so check the actual creation
date rather than counting from today.

The decision made, after going back and forth: **wait it out.** A fresh
Gmail would work around it, but that is another account to manage and
the user is not launching this week anyway. When it unlocks, create the
channel as a **Brand Account** — that keeps the channel separate from
the login so managers can be added or ownership transferred later.
Cannot be changed after creation.

## Infrastructure, for context only — it is web-steward's

`opitrics.com` registered at Cloudflare. Workspace verified, MX live and
confirmed resolving. SPF and DKIM still missing; neither blocks
anything, both help outgoing mail avoid spam. Aliases per platform, one
seat.

## What is genuinely open

**1. The sources URL, and it has a real deadline.** Video descriptions
and threads embed `--sources-url` permanently and cannot be edited at
scale. Whether it resolves to `opitrics.com/{subject}/` or
`theshidiq.github.io/opitrics-sources/{subject}/` must be settled
**before the first upload**, not after. `CLAUDE.md`'s run order now
shows the `opitrics.com` form, so web-steward may have already decided
— confirm rather than assume, and confirm the deploy actually serves
that URL before anything ships against it.

**2. Instagram automation is gated on hosting, not on credentials.**
`opitrics/publish/meta.py` documents it: Meta does not accept an
upload. It is handed a **public URL and fetches the file itself**, so a
local path cannot be used and neither can an authenticated link. The
shorts are local files and nothing in the project serves them
publicly. Until that is solved, working API credentials publish
nothing. Hosting is web-steward's call — raise it there before any
further Meta app setup.

Also on Instagram, from the same file: Business or Creator account
linked to a Facebook Page, an app with `instagram_basic` and
`instagram_content_publish`, and App Review before serving beyond 25
test users. Publishing to the user's own account should fall inside
those 25 — worth confirming rather than assuming a 2–4 week review is
required. Note the Facebook Page is created *by* a personal Facebook
account; that link is invisible to viewers but real inside Meta, and it
is the one place the anonymity could quietly leak.

**3. The permalink promise never appears on screen.** Every bio claims
every number links to its source, but on the shorts that promise lives
only in the description and the audit pages. A viewer who never taps
through sees the watermark and nothing else — and that promise is the
entire differentiator. Render-layer change, so pipeline work to hand
back, but it is a content problem and worth raising.

**4. A Meta developer MCP is installed** (`meta_developer_tools`,
`https://mcp.facebook.com/devtools`, official and verified), registered
at project scope in `~/.claude.json`. `claude mcp list` reports it
connected.

**Its tools are reachable from the terminal CLI only, not the desktop
app.** The OAuth was completed via `/mcp` in a terminal session and the
token lives in that CLI's credential store; the desktop app does not
read it and has no `/mcp` command to run the flow itself. An earlier
note in this file predicted a fresh desktop session would pick the
tools up — that was wrong, and two sessions wasted time on it. It is
not stale state and not a dropped connection: the terminal is
authenticated and the desktop app never was.

Either run `claude` in a terminal for Meta MCP work, or skip it. It
reads docs, app config, App Review status and rate limits — all of
which are visible in the Meta dashboard. Convenience, not a dependency,
and it does not touch the hosting problem that actually gates
Instagram. The one useful question it would answer, whether App Review
is needed to publish to your own account, is settled faster by adding
yourself as a test user and trying it.

## How this session worked, since it differs from the briefs

The main assistant owns account management, cadence, and what ships;
`social-strategist` is consulted for editorial judgment and argued
with, not handed the decision. That split is recorded in `CLAUDE.md`
and both briefs — this note is only flagging that it changed recently,
so older habits in a transcript may not match.

The strategist consultation on the Japanese arm was substantial and its
conclusions are already committed into `brand/PROFILE.md` and
`CLAUDE.md`. Do not re-litigate it from scratch; read those first.

## The one thing worth doing next

Content. Five English shorts are rendered and unposted. Nothing about
the YouTube wait blocks X or TikTok, and the profiles can be filled in
today from `brand/PROFILE.md`.

The real decision waiting is which short goes first, how the rest are
sequenced, and what the launch post says — with the sources URL settled
first, because it goes into every description.
