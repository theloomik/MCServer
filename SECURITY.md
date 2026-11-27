# Security

## Reporting a problem

Please report security problems **privately** through
[GitHub's security advisories](https://github.com/theloomik/MCServer/security/advisories/new),
not as a public issue. You'll get an answer as soon as possible; please give us a reasonable time
to fix the problem before telling others about it.

Only the latest release gets security fixes.

## What MCServer does on your PC

- **Runs the server JAR you choose** with your user's rights (no administrator rights). Only use
  JAR files from sources you trust. Server files MCServer downloads come only from PaperMC's and
  Mojang's official APIs and download servers, and are checked against their published checksums
  before use.
- **Network:** besides those downloads, MCServer contacts nothing on the internet. It sends no
  analytics or telemetry. The "Players connect to" address is read from this PC; nothing is sent
  to find it.
- **Files:** everything stays in `%LOCALAPPDATA%\MCServer`. MCServer never deletes server files
  permanently; deleted servers, worlds and backups go to the Recycle Bin.
- **Server processes** are tied to MCServer (a Windows Job Object), so a server does not keep
  running hidden if MCServer itself crashes.
