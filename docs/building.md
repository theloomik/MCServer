# Building the Windows app and installer

MCServer 2.0 ships as a normal Windows program: a folder with `MCServer.exe` that runs
without Python, and an installer that puts it on the Start menu. One command builds both.

## What you need

- Windows 10 or 11, 64-bit.
- The project's virtual environment with the dev dependencies (`uv sync`), which include PyInstaller.
- [Inno Setup 6](https://jrsoftware.org/isdl.php) (6.6 or newer) for the installer. The build finds
  it in the usual install folders or on `PATH`; otherwise pass `--iscc`.

## Build

From the repository root:

```powershell
.venv\Scripts\python tools\build_windows.py
```

Only the app folder, without the installer:

```powershell
.venv\Scripts\python tools\build_windows.py --skip-installer
```

The build:

1. reads the version and identity from `src/mcserver/__init__.py`;
2. draws `MCServer.ico` (16–256 px) and the installer images from the logo embedded in the app;
3. writes the Windows version resource (Explorer → Properties → Details);
4. runs PyInstaller with `packaging/windows/MCServer.spec`;
5. runs Inno Setup with `packaging/windows/MCServer.iss`.

## Output

| Path | What it is |
|------|------------|
| `dist/windows/MCServer/MCServer.exe` | The standalone app (about 60 MB folder). It can be zipped and run from anywhere. |
| `dist/windows/MCServer-<version>-setup.exe` | The installer (about 20 MB). |
| `build/windows/` | Intermediate files (icon, images, version resource, PyInstaller work folder). |

`build/` and `dist/` are ignored by Git; never commit what the build produces.

## Changing the version

Edit `__version__` in `src/mcserver/__init__.py`. `pyproject.toml`, the About dialog, the exe's
details and the installer all read it from there. Windows needs a numeric file version, so
`2.0.0a1` becomes `2.0.0.0` in the file details; the full text stays in "Product version".

## Where things go on the user's PC

| What | Where |
|------|-------|
| Program (installed for the user, the default) | `%LOCALAPPDATA%\Programs\MCServer` |
| Program (installed for all users, needs administrator rights) | `C:\Program Files\MCServer` |
| Servers, worlds, backups, settings | `%LOCALAPPDATA%\MCServer\servers` |
| Start menu shortcut | `MCServer` (a desktop shortcut is optional) |

User data never lives in the program folder, so upgrading or uninstalling never touches it.
The uninstaller removes only the files it installed; the servers folder stays until the user
deletes it.

Run from source (`python -m mcserver.presentation`), MCServer uses `minecraft_servers` in the
current folder instead, so development never touches the data of an installed copy.

## Packaging notes

- **One folder, not one file.** A one-file exe unpacks itself to `%TEMP%` on every start: slower,
  and more often flagged by antivirus software. The installer installs the folder.
- **No console.** The exe is a window application. Java is started with `CREATE_NO_WINDOW`, so
  neither the Java check nor a running server opens a console window.
- **Left out of the bundle.** Qt parts MCServer does not use (Qt Quick/QML, Qt PDF, software
  OpenGL, the virtual keyboard, extra image formats, Qt's own translations) are filtered out in
  the spec, which halves the size. If a future feature needs one of them, remove it from
  `UNUSED` in `packaging/windows/MCServer.spec`.
- **No UPX.** Compressed executables start slower and trigger antivirus false positives.
- **Running app.** MCServer holds the mutex `MCServer.2.Running`; the installer and uninstaller
  ask the user to close MCServer first (so servers stop properly) instead of closing it themselves.
- **Taskbar identity.** The app sets the AppUserModelID `MCServer.MCServer.2`, and the shortcuts
  carry the same one, so the taskbar shows MCServer's icon and groups its windows.
- **Not signed.** The exe and installer are not code-signed yet, so Windows SmartScreen warns on
  first run ("Windows protected your PC" → More info → Run anyway). Signing needs a certificate.

## MCServer 0.9.1

The old `MCServer.spec`, `build.ps1` and `installer/setup.iss` in the repository root build
MCServer 0.9.1 and are left as they were. The 2.0 installer has its own AppId, so it installs next
to 0.9.1 rather than replacing it; both use the same servers folder.

## Checking a build

Before publishing an installer, on a PC (ideally one without Python):

1. Install it, start MCServer from the Start menu, check the icon in the title bar and taskbar.
2. Settings → Help → About MCServer shows the right version.
3. Java is found; create or import a server, start it, stop it. No console window appears.
4. Switch the language and the theme.
5. Uninstall from Settings → Apps; `%LOCALAPPDATA%\MCServer\servers` is still there.
