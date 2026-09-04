# The bot (optional)

barebonesCRM works with no automation at all. You log conversations by hand in the Log,
set follow-up dates, and the Today view is your reminder. Stop reading here if that is enough.

If you want the board to know about replies without you typing them in, you add a **bot**:
any process that reads your mail and writes three JSON files. This repo does not ship the bot.
It ships the contract the bot writes to and the UI that renders it. This page is that contract
plus one worked example.

## The rule that makes it safe

Two writers share one repo without clobbering each other because they own different files.

| Owner | Files | Who writes |
|---|---|---|
| **You** | `leads.json` `organizations.json` `campaigns.json` `followups.json` | the UI, or you by hand |
| **Bot** | `observations.json` `comments.json` `inbox/unmatched.json` | the bot, append-only |

The bot **never** writes a human-owned file. Not to fix a typo, not to set a state it is sure
about. It records what happened and suggests. The UI merges bot-over-nothing and human-over-bot:
a suggestion shows only where you have not decided that field yourself, and a decision you make
is never undone by the next run.

Every bot run is: `git pull`, read mail, write its three files, verify they parse, commit its
three files only, `git push`. If nothing changed, no commit.

## The three files

### `comments.json`

An array. This is the Log the Person view shows, so bot entries and your own notes live in the
same list. A bot entry:

```json
{
  "key": "outreach:jane-doe",
  "author": "CRM Bot",
  "via": "bot",
  "channel": "email",
  "text": "They replied. Asks for a review copy.",
  "link": "https://mail.google.com/mail/u/0/#all/18f3a2b1c4d5e6f7",
  "ts": "2026-09-04T05:40:56Z"
}
```

- `key` is the lead id.
- `text` is one factual line. What happened, not what to do about it.
- `link` opens the actual message. The UI renders it as an arrow next to the line. Always set
  it. For channels that do not email you the message body, it is the only way to read it.
- Dedup rule: skip if an entry with the same `key`, same `link` and same calendar date exists.
  Bots get run twice. Make the second run a no-op.

### `observations.json`

An object keyed by lead id. One entry per lead the bot has an opinion about.

```json
{
  "outreach:jane-doe": {
    "lastInbound": "2026-09-04T05:40:56Z",
    "needsAction": true,
    "suggestedState": "replied",
    "reason": "reply arrived (email)",
    "ts": "2026-09-04T06:30:28Z"
  }
}
```

- `needsAction: true` puts the lead on Today with a "reply, act" badge. Set it when a reply
  arrives and the lead's `waiting` is `them`. A real reply beats a stale waiting-timer. Also set
  it on a bounce, because a bad address needs fixing.
- `suggestedState` is a hint. The Person view shows it only when it differs from the state you
  set. Never suggest something that contradicts a decision you made after the event.
- Overwrite the entry each run. This file is the bot's current view, not a history.

### `inbox/unmatched.json`

An array of inbound messages the bot could not match to any lead.

```json
[{
  "from": "sam@somewhere.example",
  "name": "Sam Example",
  "subject": "Re: your talk",
  "date": "2026-09-04T05:40:56Z",
  "link": "https://mail.google.com/mail/u/0/#all/18f3a2b1c4d5e6f7",
  "channel": "email",
  "guessOrg": "Somewhere"
}]
```

The bot never creates a lead. You decide whether an unmatched sender becomes one. The
**Unmatched** tab lists these entries. **Promote** creates the lead and its organization in
the campaign you pick, stores the email or LinkedIn profile URL on the lead so the bot matches
that person from then on, and drops the entry. **Dismiss** drops it without creating anything.
Both are single commits. For LinkedIn entries, `from` must be the profile URL, since that is
what gets stored as `handles.linkedin`.

## Matching

The bot resolves a message to a lead in this order, stopping at the first hit:

1. `gmailThreadId` on the lead, if the message is on that thread.
2. Any address in the lead's `emails` array.
3. `handles.linkedin` on the lead, for LinkedIn notifications.
4. Lowercased full name, as a last resort.

Matching is only as good as the data you imported. A CSV with no email column gives the bot
nothing to match on. Fill `emails` and, where it matters, `handles.linkedin`, and fewer
messages land in unmatched.

## Prerequisites, all of them, before you start

Whatever runs the bot, you need:

1. **Leads already in the CRM.** The bot matches mail against `leads.json`. Run the CRM,
   import your CSV, then add the bot. Not the other way round.
2. **A git remote the bot can push to.** Your private fork on GitHub, with write access for
   whatever runs the bot. Both the bot and your laptop pull before every write, so the remote
   is the single source of truth.
3. **A mail source the bot can read.** One of:
   - A hosted agent with a mail connector. Zero code, but a paid tier. See the example below.
   - IMAP with an app password. About forty lines of Python's standard library. Cheapest.
   - The Gmail REST API. A Google Cloud project, an OAuth consent screen, a credentials file,
     a token refresh flow, and a dependency. Correct, and the most setup by far.
4. **A schedule.** Once a day is enough. cron, launchd, a hosted routine, whatever you have.
5. **If you want LinkedIn**, turn on LinkedIn's daily messaging-digest email in LinkedIn
   settings, so DMs reach the same inbox as a notification. The digest carries the sender's
   name, profile URL and a "View message" link, and no message text.

Two things to know in advance:

- **A quiet day leaves no commit.** Silence is not failure. Check the runner's own log before
  concluding the bot is broken.
- **Pull before hand-editing.** The UI pulls for you on every save. If you edit a JSON file in
  an editor, `git pull` first, or your push will fight the bot's overnight commit.

## Worked example: a hosted agent with a Gmail connector

This is the setup the author runs: a scheduled Claude Code routine with the Gmail connector,
pushing to a private GitHub repo once a day. Nothing to host, nothing to install. It needs a
Claude plan that includes routines and connectors.

Setup order:

1. Fork this repo. Make the fork **private**. Import your leads.
2. In claude.ai, connect Gmail.
3. Create a routine on a daily cron. Give it the repo and the prompt below.
4. Wait for one run. `git pull`. Reload the board.
5. Open the **Unmatched** tab. Promote the senders who belong in a campaign, dismiss the
   rest. Each promotion stores the address or profile URL, so the next run matches that
   person on its own. Expect this list to be long after the first run and short after a
   week.

The prompt, with the author's specifics removed. Replace the bracketed parts.

```
You maintain a single-user outreach CRM for [your name] about [what you are pitching].
The data model is normalized JSON at the repo root.

HUMAN-OWNED. You NEVER write these: leads.json, organizations.json, campaigns.json,
followups.json.
YOUR FILES. The only ones you may write: observations.json, comments.json,
inbox/unmatched.json.

Your job: record what transpired on the communication channels below, and reconcile
status the user has NOT decided, never overriding a field the user set. You are a cleanup
pass. The user's UI actions always win.

SETUP each run:
1. git pull.
2. Load leads.json. Build lookups: byEmail (each lead.emails[] -> lead.id), byThread
   (lead.gmailThreadId -> lead.id), byLinkedin (lead.handles.linkedin -> lead.id),
   byName (lowercased lead.name -> lead.id). Note each lead's state, waiting, followUpDate.
3. Load campaigns.json for each campaign's states (key -> kind active|won|lost).
4. Load observations.json (default {}), comments.json (array), inbox/unmatched.json (array).

FEEDS, read via the Gmail connector:
A. EMAIL. in:inbox newer_than:2d -from:me; a bounce search (subject:undeliverable OR
   subject:"delivery status" OR from:mailer-daemon OR from:postmaster) newer_than:2d;
   and in:sent newer_than:2d. Keep only genuine replies, bounces, out-of-office and intros
   about [your topic]. Ignore newsletters and billing or platform notifications. Resolve
   each to a lead by byThread(threadId) then byEmail(sender). channel="email".
   LINK = https://mail.google.com/mail/u/0/#all/<threadId>.
B. LINKEDIN (optional). from:messaging-digest-noreply@linkedin.com newer_than:2d. The
   body gives the sender's full name, profile URL and a "View message" link, with no
   message text. Resolve by byLinkedin(profile URL) then byName(full name).
   channel="linkedin". LINK = the View-message URL. Inbound only.

FOR EACH resolved event:
1. APPEND to comments.json:
   {"key":"<lead.id>","author":"CRM Bot","via":"bot","channel":"<email|linkedin>",
    "text":"<one factual line>","link":"<LINK>","ts":"<ISO 8601 Z>"}
   Always include link. Email text is the observed fact only: "They replied. Asks for a
   review copy." / "Bounced: address not found." / "Out of office until 17 Aug." /
   "Emailed them." LinkedIn text: "LinkedIn: <Full Name> messaged you (open to read)."
   Dedup: skip if an entry with the same key, same link and same calendar date exists.
2. RECONCILE into observations.json (never leads.json):
   observations.json["<lead.id>"] = {"lastInbound":"<ISO Z|null>","needsAction":<bool>,
     "suggestedState":"<state key|null>","reason":"<short>","ts":"<ISO Z>"}
   If a reply arrived on either channel AND the lead's waiting == "them", set
   needsAction:true, reason "reply arrived (<channel>)". Bounce -> needsAction:true.
   suggestedState is a suggestion only. Never suggest something that contradicts a
   decision the user made after the event.
3. UNMATCHED: if the event resolves to no lead, append to inbox/unmatched.json:
   {"from":"<addr or profile>","name":"<name>","subject":"<subj>","date":"<ISO Z>",
    "link":"<LINK>","channel":"<email|linkedin>","guessOrg":"<org or ->"}
   Do NOT create a lead. Do NOT change any status.

VERIFY before commit:
  python3 -c "import json;[json.load(open(f)) for f in ['observations.json','comments.json','inbox/unmatched.json']]"
  If it fails: git checkout -- observations.json comments.json inbox/unmatched.json
  and do NOT commit.

COMMIT, only your files, ever:
  git config user.email bot@localhost; git config user.name "CRM Bot"
  git add observations.json comments.json inbox/unmatched.json
  git commit -m "auto: comms refresh <YYYY-MM-DD>"; git push origin main
  If nothing changed, do not commit.

LABEL: ensure a Gmail label "CRM" exists and apply it to the threads you kept. That is
your only Gmail write.

PRINT a short digest: Needs action / Awaiting them / LinkedIn / Unmatched; then the
commit hash, or "No new activity."
```

## Worked example: a local script

Same contract, no hosted agent. The skeleton is: pull, read IMAP for the last two days,
match, write the three files, verify, commit, push. Run it from cron. Python's `imaplib`,
`email` and `json` modules cover all of it with no install. The matching order and the dedup
rule above are the parts worth getting right. Everything else is plumbing.
