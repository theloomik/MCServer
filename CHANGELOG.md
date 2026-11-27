# Changelog

## 2.0.0 — 2026-11-28

MCServer 2.0 is a complete rewrite: a new interface, a new core and a proper Windows installer.

### New

- **Create a server in a minute** — download Paper or Vanilla straight from PaperMC or Mojang
  (checked against the published checksums), or use your own server JAR. Memory is picked with a
  slider sized for your PC.
- **Import a server folder** you already have; folders from elsewhere are copied, never changed.
- **Safe start, stop and restart** — Stop waits for the world to be saved; Kill only when needed;
  optional automatic restart after a crash; a server never keeps running hidden after MCServer
  closes.
- **Live console** with command history, a warnings filter and saving the output to a file.
- **Overview** of players, memory, CPU and uptime, with charts of the last minutes.
- **server.properties editor** with readable names, groups and search.
- **Worlds** — create, import (folder or ZIP), export, switch and delete worlds.
- **Backups** — one click or scheduled, with restore that first saves the current state.
- **Setup guide** on the first start, **light and dark theme** (following Windows), **English and
  Ukrainian**.
- **Installer** for the current user, without administrator rights; **About** dialog; MCServer's own
  log file for bug reports.

### Changed from 0.9.1

- The playit.gg tunnel is gone: MCServer shows the address for your local network; playing over the
  internet needs port forwarding on your router.
- The server download covers Paper and Vanilla; other server types work with **Use a JAR file…**.
- The installer no longer installs Java. MCServer finds the Java on your PC and explains what to do
  if there is none (Minecraft 1.20.5+ needs Java 21).
- MCServer 2.0 installs next to 0.9.1 instead of replacing it. Your 0.9.1 servers stay in
  `%LOCALAPPDATA%\MCServer\servers`; add them with **Import server folder…**. Uninstall 0.9.1
  whenever you like; your servers are kept.

### Known limitations

- The installer and app are not code-signed yet, so Windows SmartScreen warns on first run
  (**More info → Run anyway**).
- One server runs at a time.
