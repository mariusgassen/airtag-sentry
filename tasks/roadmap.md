# Roadmap

A forward-looking, prioritized backlog — distinct from `tasks/todo.md`,
which is the historical changelog of what's already shipped (v1–v10).
Items here are ideas and their rationale, not commitments; each gets moved
into `todo.md` (with a `vN:` entry) as it's actually built.

Compared against [Traccar](https://www.traccar.org/) (a mature open-source
GPS platform) for feature inspiration where noted below.

## 1. "Moved without you" alert correlation — in progress

Find My (and this app's existing movement detection) can tell you an item
moved *relative to its own history*, but not whether it moved *while you
weren't with it* — the actual signal that distinguishes "someone took my
bike from the garage while I was at work" from "I rode my bike to the
store." Apple's `FindMy.py`/search-party protocol (used for AirTags) mostly
only reports a device that's off, dead, or in airplane mode, so a live
phone's location has to come from a different source: Apple's classic Find
My iPhone web service (`fmipservice`, the same one behind `icloud.com/find`)
via the `pyicloud` library, as a second, independent Apple session/login.

Produces a new `moved_without_owner` alert reason, fired *in addition to*
(never replacing) the existing movement alerts, when a real movement alert
already fired **and** the tag's new position is far from the owner's
last-known phone location.

Status: **done** — see `tasks/todo.md` v11.

## 2. Visualize owner location on the map

Fast-follow to (1): a distinct marker for the owner's last-known position,
reusing `MapCard.tsx`'s existing pulsing "Aktueller Standort" dot pattern
but sourced from the new `GET /api/owner-location` endpoint instead of the
browser's own geolocation. Small, mostly frontend.

## 3. Home/geofence zone

Traccar-style: define a home/safe zone (radius or drawn polygon) per AirTag
or globally; alert specifically on leaving it, with optional dwell-time and
schedule rules (e.g. only armed overnight). Doesn't need any phone-tracking
infrastructure at all — a good self-contained complement to (1)/(2) for
anyone who doesn't want a second Apple login, and a proven pattern (Traccar
users rely on this as their primary alerting mechanism).

## 4. Alert history view

The `alerts` table already stores full history; the dashboard only ever
surfaces the single latest one (`/api/status`'s `last_alert`). Cheap, high
value: a scrollable list per AirTag, same shape as the existing
"Verlauf" (location history) collapsible section in `AirtagDetail.tsx`.

## 5. Trip/stop report per AirTag

Traccar-style: "here's every place it stayed more than X minutes this
week," built entirely from existing `location_reports` — no new data
source needed, just a report view over what's already stored.

## 6. Per-AirTag alert snooze

Mute alerts for a chosen duration (e.g. "I'm riding my own bike right now")
without touching the global movement thresholds in Settings. Standard
false-positive-fatigue mitigation for any motion-based alarm.

## 7. Per-AirTag notification routing

Every configured notifier (ntfy/Telegram/push) currently fires for every
AirTag. Multi-item households may want e.g. only Telegram for the bike,
only push for the backpack.

## 8. Location-history retention/pruning

`location_reports` grows unbounded. Add a retention-period setting and a
periodic prune job (or a `DELETE ... WHERE timestamp < now() - interval`
run alongside the scheduler).

## 9. Battery-level surfacing

`FindMy.py`'s location report exposes a `status` byte for the accessory,
which likely encodes battery state (needs confirming against the library/
protocol). If so: surface it in the dashboard and optionally alert on low
battery, so a dying AirTag doesn't just silently stop reporting.

## 10. Move Apple login flows into the dashboard UI — done

Per `CLAUDE.md`'s UI-first constraint: `python -m airtag_sentry login` and
`login-owner` are currently CLI-only interactive scripts
(`input()`/`getpass.getpass()`), not because Apple's login protocol
requires a terminal, but because that's how they were first built. Both are
a small multi-step state machine (submit Apple ID + password → if 2FA
required, pick a method and submit a live code → session persisted) that
maps cleanly onto a dashboard form: a "Connect Apple ID" panel (Settings or
AirTags), a password field, then a 2FA code field that appears if
`requires_2fa`/`LoginState.REQUIRE_2FA` is returned. The main design
question is where the in-progress (password-submitted, 2FA-pending)
`AppleAccount`/`PyiCloudService` object lives between the two requests -
this app is single-user, so an in-process singleton keyed by nothing more
than "the one active login attempt" is enough, no session-store needed.
Status: **done** — see `tasks/todo.md` v12. The `login`/`login-owner` CLI
subcommands were removed entirely rather than kept as a redundant second
path.

## 11. CSV/GPX export

Export an AirTag's location history for a given period — useful when
reporting a theft to police.

## 12. Fallback: upload an existing `account.json` instead of live login

Real-user report (Sep 2026): a first-time AirTag-tracking login for this
Apple ID consistently failed 2FA submission with
`findmy.errors.UnhandledProtocolError: Error response for GSA request: 503`
- a raw rejection from Apple's own GSA endpoint, not a bug in this app's
code. Independently corroborated in
[malmeloo/FindMy.py#165](https://github.com/malmeloo/FindMy.py/issues/165):
another user hit the identical error on a *fresh* account.json generation
attempt, while a session generated on a real Mac worked fine afterward -
pointing at Apple's anti-automation defenses rejecting first-time login
handshakes from freshly-provisioned (non-genuine-hardware) device
identities, at least some of the time. Ruled out as a cause: anisette
device-identity persistence (already fixed, `tasks/todo.md` v12.3) and the
UI-vs-CLI login trigger (this Apple ID had never completed this flow via
the old CLI `login` command either, so it isn't a regression from the
login-UI migration).

If waiting out Apple's apparent cooldown and retrying with the same
(persisted, not re-provisioned) anisette identity doesn't eventually
succeed, the fallback used elsewhere in the FindMy.py ecosystem is: generate
`account.json` via a real Mac/genuine Apple hardware once (the same
`FindMy.py`/keychain mechanism this project's README already documents for
*AirTag key* extraction, just applied to the *account* session instead),
then let the dashboard accept an upload of that file directly - bypassing
the live SRP+2FA handshake this app currently always performs. Would need:
a new `POST /api/apple/session` (multipart upload) validating the JSON
shape before writing it to `APPLE_STORE_PATH`, and an "Upload session
file" option alongside the existing login form in `AppleConnectPanel.tsx`
(or a variant of it). Only worth building if the wait-and-retry path turns
out not to work for this account.

## 13. Blocked on upstream: AirTag key extraction without a Mac (rustpush)

The README's "Getting started" still has exactly one step that isn't a
dashboard flow: step 2, "Extract your AirTag's key," which requires a Mac
with the AirTag paired in Find My and `python -m findmy decrypt` reading
the local macOS keychain. Per `CLAUDE.md`'s UI-first constraint, that's the
one case here where "there's a real technical reason a browser request
can't do it" - `FindMy.py` (the library this app depends on for all Apple
offline-finding protocol work, see `README.md`) has no way to pull that key
material without genuine Apple hardware.

[malmeloo/FindMy.py#173](https://github.com/malmeloo/FindMy.py/issues/173)
(opened by the library's own maintainer, Sep 2025) tracks closing exactly
that gap: importing accessory secrets straight from iCloud Keychain, no Mac
needed, via [rustpush](https://github.com/OpenBubbles/rustpush), a Rust
reimplementation of Apple's push/iMessage/iCloud protocols with a working
CloudKit keychain-sync client. A beta implementation now exists:
[malmeloo/findmy-export](https://github.com/malmeloo/findmy-export), a Rust
CLI built on a not-yet-upstreamed rustpush fork (`malmeloo/rustpush@next` -
the issue's "upstream changes to rustpush" TODO is still open). Cloned and
read its source directly (its README has no usage docs beyond a TODO list)
to verify what it actually requires, since that determines whether it's
usable here at all:

- **CLI surface** (from `src/main.rs`, undocumented in the README):
  `findmy-export --apple-id <email> [--anisette-url <url>]
  [--output-dir <dir>]`, prompting interactively for password/2FA.
- **Does its own Apple login - does not reuse `auth.py`'s session.** The
  "Inherit session from FindMy.py" / "Inherit Anisette session from
  FindMy.py" TODOs are both unchecked. It logs in as a fake spoofed iPhone
  (`FakeIOSConfig`) with its own local state dir, entirely separate from
  this app's `APPLE_STORE_PATH` session.
- **Bigger prerequisite than "own a Mac": needs another trusted device's
  passcode.** Beyond Apple ID + 2FA, step 5 joins the iCloud Keychain
  "trust circle" via *escrow* - it lists "escrow bottles" (one per other
  device already in your Keychain circle) and then prompts for **that
  device's unlock passcode** to decrypt one. It hard-errors ("No escrow
  bottles found. Make sure you have another trusted device.") if none
  exist. For this app's actual use case - one person extracting their own
  AirTag keys - that's arguably a *harder* ask than the current Mac
  requirement: a Mac already signed into the same Apple ID satisfies
  Keychain sync locally with no extra secret; this instead wants a second
  device's lock-screen passcode entered into a beta third-party tool over
  the network.
- **Output format needs a translation step.** Writes one XML **plist**
  per accessory (fields `privateKey`/`sharedSecret`/
  `secondarySharedSecret`/`secureLocationsSharedSecret`/`publicKey`/
  `identifier`/`model`/`pairingDate`/`name`/`emoji`), not `FindMy.py`'s own
  JSON export shape. It likely isn't a drop-in for this app's
  `accessory_json` upload path (`FindMyAccessory.from_json`,
  `web/app.py`'s `/api/airtags/{id}/key`) without confirming the schemas
  line up. The narrower `private_key_b64` path
  (`KeyPair.from_b64`, already supported in the dashboard's key form) is
  more promising in principle - the plist's `privateKey` field is exactly
  that raw key, base64-encoded - but going from "AirTag master key" to
  full rolling-identifier lookups the way `FindMy.py` needs hasn't been
  verified end-to-end against a real export.

Given all of that - unmerged rustpush fork, undocumented CLI, a second
full Apple login with no session reuse, a device-passcode prerequisite
that's a net *downgrade* in convenience/trust surface versus "own a Mac,"
and an unconfirmed output-format handoff - this isn't ready to become the
new documented path in the README, and definitely not ready to become a
dashboard flow (CLAUDE.md's UI-first constraint doesn't cover asking a user
to paste another device's passcode into a third-party beta binary). Revisit
once: rustpush's changes land upstream, `findmy-export` actually inherits
this app's existing Apple/Anisette session instead of doing a second login,
and the escrow/passcode step either goes away or is confirmed unavoidable
for a single-user single-device setup (session inheritance might imply the
requesting session itself already counts as a "trusted device," avoiding
the second-device passcode entirely - unconfirmed either way).
