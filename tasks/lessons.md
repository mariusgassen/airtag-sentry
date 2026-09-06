# Lessons

Corrections from the user get logged here as they happen, with the pattern and the
rule adopted to prevent repeating it.

## Built a CLI-only setup step without questioning it
When implementing owner device tracking (v11), I added `login-owner` as a
CLI subcommand, mirroring the existing `login` command's shape, without
asking whether it should instead be a dashboard UI flow — even though this
app already handles OAuth, encrypted key upload, and settings entirely
through the UI. The user pushed back: "Everything should be done from the
UI if possible."
**Rule**: default to a UI flow for anything the user needs to set up or
operate, in this repo and in general for apps that already have a web UI.
Only reach for a CLI step when there's a genuine technical blocker to doing
it from the browser - "the existing similar code did it this way" is not
such a blocker. Recorded as a hard constraint in `CLAUDE.md`.
