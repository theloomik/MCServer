; Inno Setup 6 script for MCServer 2.0 (M5). Build with tools\build_windows.py, which passes every
; value below (version, paths, images) with /D, read from src\mcserver\__init__.py.
;
; Installs for the current user by default (no administrator rights needed) into
; %LOCALAPPDATA%\Programs\MCServer; "Install for all users" is offered and needs administrator rights.
; User data (servers, worlds, backups, settings) lives in %LOCALAPPDATA%\MCServer\servers, never in the
; installation folder, so upgrading or uninstalling never touches it.

#ifndef AppVersion
  #error Build with: .venv\Scripts\python tools\build_windows.py
#endif

[Setup]
; Never change AppId: Windows recognises upgrades and the uninstaller by it.
; (Different from MCServer 0.9.1's, so installing 2.0 never removes 0.9.1 behind the user's back.)
AppId={{E6DDD048-24E9-4439-958E-EF2C855DE65F}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppCopyright={#AppCopyright}
AppPublisherURL={#AppHomepage}
AppSupportURL={#AppHomepage}/issues
AppUpdatesURL={#AppHomepage}/releases
VersionInfoVersion={#AppFileVersion}
VersionInfoProductName={#AppName}
VersionInfoProductTextVersion={#AppVersion}
VersionInfoDescription={#AppName} Setup
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UsedUserAreasWarning=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
SourceDir={#SourceDir}
OutputDir={#OutputDir}
OutputBaseFilename={#AppName}-{#AppVersion}-setup
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
WizardStyle=modern dynamic
WizardImageFile={#WizardLarge}
WizardSmallImageFile={#WizardSmall}
; "modern dynamic" follows Windows' dark mode and has its own images for it: use the logo there too.
WizardImageFileDynamicDark={#WizardLarge}
WizardSmallImageFileDynamicDark={#WizardSmall}
Compression=lzma2/max
SolidCompression=yes
ShowLanguageDialog=auto
; MCServer holds this mutex while it runs: Setup asks the user to close it (servers stop properly),
; rather than closing it itself.
AppMutex=MCServer.2.Running,Global\MCServer.2.Running
CloseApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "ukrainian"; MessagesFile: "compiler:Languages\Ukrainian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; An upgrade replaces the bundled libraries entirely, so none from an older version linger.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; AppUserModelID: "MCServer.MCServer.2"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; AppUserModelID: "MCServer.MCServer.2"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

; No [UninstallDelete]: the uninstaller removes only the files it installed. Servers, worlds, backups
; and settings in %LOCALAPPDATA%\MCServer stay where they are.
