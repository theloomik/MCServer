# MCServer

A desktop Minecraft server manager for Windows. It allows you to create, run, and manage
multiple servers via a user-friendly graphical interface — without the command line.

## Features

- Run PaperMC, Purpur, Spigot, Fabric, Forge, and Vanilla servers
- Real-time RAM, CPU, TPS, and player count monitoring
- Edit `server.properties` directly inside the application
- Public access via a TCP tunnel (no registration or static IP required)
- Automatic installation of Java 25 during the first run of the installer

## Requirements

| Component | Version |
|-----------|---------|
| Windows   | 10 or newer (64-bit) |
| Java      | 25+ (JRE) |

> **The installer will install Java 25 automatically** if an internet connection is available.
> If Java is already present on the computer but its version is lower than 25, the installer will prompt to update.

## Installation

1. Download `MCServer_Setup_vX.X.X.exe` from the [Releases](../../releases) section.
2. Run the installer as administrator.
3. Once completed, a shortcut will appear on the desktop and in the Start menu.

## Data Locations

All files that change during application operation are stored outside the installation folder:

| What | Path |
|------|------|
| Server folders (worlds, plugins, configs) | `%LOCALAPPDATA%\MCServer\servers\` |
| Application settings | `%LOCALAPPDATA%\MCServer\servers\app_settings.json` |
| Downloaded tunnel agent | `%LOCALAPPDATA%\MCServer\playit.exe` |

> To back up a server, copy the corresponding folder from `%LOCALAPPDATA%\MCServer\servers\`.
> Data is preserved between application updates and after uninstallation.

## Security Model

### Tunnel (Public Access)

MCServer uses [playit.gg](https://playit.gg) in guest mode — **no registration required**.
The agent is downloaded from GitHub Releases and verified against a SHA-256 checksum.
The tunnel opens only the specified server port; all other traffic is not routed.

### Server JAR Files

MCServer executes the JAR file that you specified when creating the server.
**Do not run JAR files from unknown sources.** The server JAR runs with the same
permissions as MCServer (current user level, without privilege elevation).

### Network

- The installer downloads the Java JRE exclusively from `api.adoptium.net` and verifies the SHA-256 after downloading.
- The application does not collect analytics and does not send data to the internet, except for launching the tunnel and requesting the public IP address via `api.ipify.org`.
