# ADR 0008: Backups and Restore

**Status:** Accepted

## Context

Backups are a headline feature of MCServer 2.0. A server folder holds the world, plugins and settings, which people care about, plus caches and logs, which can be rebuilt. A backup has to be consistent while the server keeps running, and a restore must never leave the user with less than they had before. Nothing in MCServer deletes user files permanently by default (ADR 0004).

## Decision

- **Format.** Each backup is a ZIP archive plus a JSON metadata file (`format_version: 1`) in `<servers root>/.backups/<server_id>/`. IDs look like `YYYYMMDD-HHMMSS-<kind>[-n]`, and the kinds are `manual`, `safety` and `scheduled`. The servers root is the only place backups are stored. A list entry whose archive or metadata is missing or unreadable is skipped and never shown as a usable backup.
- **Contents.** The whole server folder except `cache`, `libraries`, `versions`, `logs`, `crash-reports`, `debug`, `.mcserver` and `session.lock` files. These are rebuilt by the server or belong to MCServer itself.
- **Writing.** Free disk space is checked first. The archive is written as `.zip.partial` and renamed only once it is complete, so a crash or full disk never leaves a half-written file that looks valid.
- **Online backups.** When the server runs, MCServer sends `save-off`, then `save-all flush`, and waits for the server's `Saved the game` line, which is checked on real Paper and Vanilla 1.21.11. Only then is the folder archived. `save-on` is sent in a `finally` block, so a failure does not leave world saving off. If the confirmation does not arrive within 120 s, the backup fails and nothing is stored. A backup is refused while the server is starting or stopping.
- **Restore only while stopped.** Restoring a running server is refused (`ServerIsRunning`), and the GUI disables the button and says why. Every restore first creates a `safety` backup of the current state. The archive is then extracted into a staging folder, checking for paths that escape the folder (zip-slip) and verifying CRCs. Next, the current folder is renamed aside, the staging folder takes its place, and the excluded items (caches, logs, MCServer state) are moved back. Finally, the old folder goes to the Recycle Bin, or to `.trash` if the Recycle Bin is unavailable.
- **Interrupted restores.** At startup, `recover_interrupted_restores` puts the original folder back, or finishes a swap that had already happened, based on the staging and aside folders left on disk.
- **Deleting a backup** moves its files to the Recycle Bin or `.trash`. They are never removed permanently.
- **GUI.** Backups is a dashboard tab with a list, a note field, *Back up now*, *Restore…* (asks twice; the second question names the backup date) and *Delete…*. Operations run in the background with progress, one at a time, and closing the window waits for them. The unclean-shutdown notice links to the server's backups.

## Consequences

Backups are portable ZIP files that users can open without MCServer. An online backup depends on the server answering `save-all flush` with the usual line; modded servers that print something else fail clearly instead of producing an unconfirmed backup. Restores need roughly twice the world size in free space while they run. This reduces the risk of losing a world, but it is not a guarantee: a disk failure or a backup folder deleted by hand still loses data, so copies on another disk remain the user's choice. Scheduled backups and retention limits are not part of this change. The `scheduled` kind is reserved for them.
