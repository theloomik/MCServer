# ADR 0010: Downloading Official Server JARs

**Status:** Accepted

## Context

Most people creating a server do not have a server JAR yet. Users should be able to get one from inside MCServer without visiting download sites, and nothing should run that did not come from the official publisher.

## Decision

- **Sources.** Vanilla from Mojang's version manifest (`piston-meta.mojang.com`), which gives the server download, its SHA-1 and the required Java. Paper from PaperMC's Fill API v3 (`fill.papermc.io`), which gives the latest build, its SHA-256, its channel and the minimum Java. The older `api.papermc.io/v2` was retired, and calls to it now return 410.
- **Only official hosts.** Requests go over HTTPS to a fixed allowlist (`piston-meta`/`piston-data.mojang.com`, `launcher.mojang.com`, `fill`/`fill-data.papermc.io`), and redirects are checked against the same list. The User-Agent is a generic `MCServer/2.0`, and no information about the user or their servers is sent.
- **Verified or nothing.** A download is written to `<servers root>/.downloads/<file>.partial`. It is renamed only when its size and checksum match what the publisher states; otherwise the partial file is removed and the user sees why. A cached file is reused only if its checksum still matches.
- **Test versions are hidden by default.** Snapshots, pre-releases and release candidates appear only with *Show test versions*, and an experimental Paper build is labelled as such.
- **Use.** The Create server dialog offers *Download…* next to *Browse…*. The verified file is then used exactly like a browsed JAR (copied into the server folder), so server creation and its rollback are unchanged. The dialog shows the size and the Java the version needs. A download can be cancelled, and the window waits for it to stop.

## Consequences

Downloading needs internet access; without it, the dialog shows why and *Browse…* still works. Checksums prove that a file is the one the publisher listed, not that the publisher's list was not tampered with; HTTPS to the official hosts is the protection there. Verified JARs stay in `.downloads` for reuse, so they take disk space until the user removes them.
