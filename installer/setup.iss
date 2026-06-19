; MCServer Installer — Inno Setup 6
; Run via build.ps1 which sets APP_VERSION env var

#define MyAppName      "MCServer"
#define _EnvVer        GetEnv("APP_VERSION")
#if _EnvVer == ""
  #define MyAppVersion "1.0.0"
#else
  #define MyAppVersion _EnvVer
#endif
#define MyAppPublisher "LooMik"
#define MyAppExeName   "MCServer.exe"
#define MyAppSrcDir    "..\dist\MCServer"

[Setup]
AppId={{4F7A9C1E-2B3D-4E5F-8A0B-1C2D3E4F5A6B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=..\LICENSE
OutputDir=..\dist\installer
OutputBaseFilename=MCServer_Setup_v{#MyAppVersion}
#ifdef HAS_ICON
SetupIconFile=..\icon.ico
#endif
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
MinVersion=10.0
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes

[Languages]
Name: "ukrainian"; MessagesFile: "compiler:Languages\Ukrainian.isl"
Name: "english";   MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Створити ярлик на робочому столі"; GroupDescription: "Додаткові значки:"

[Files]
Source: "{#MyAppSrcDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}";            Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Видалити {#MyAppName}";   Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";      Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустити {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]

// ── Java version detection ────────────────────────────────────────────────────

function JavaMajorVersion(): Integer;
var
  TmpFile, Line, NumStr: String;
  Lines: TArrayOfString;
  I, DotPos, ExitCode: Integer;
begin
  Result := 0;
  TmpFile := ExpandConstant('{tmp}\jver.txt');
  Exec(ExpandConstant('{cmd}'), '/C java -version > "' + TmpFile + '" 2>&1',
       '', SW_HIDE, ewWaitUntilTerminated, ExitCode);
  if not LoadStringsFromFile(TmpFile, Lines) then Exit;

  for I := 0 to GetArrayLength(Lines) - 1 do
  begin
    Line := Lines[I];
    DotPos := Pos('"', Line);
    if DotPos = 0 then Continue;
    NumStr := Copy(Line, DotPos + 1, Length(Line));
    DotPos := Pos('.', NumStr);
    if DotPos > 1 then NumStr := Copy(NumStr, 1, DotPos - 1);
    Result := StrToIntDef(NumStr, 0);
    if Result = 1 then Result := 8; // Java 8 reports "1.8.x"
    Break;
  end;
end;

function NeedJava(): Boolean;
begin
  Result := JavaMajorVersion() < 25;
end;

// ── Java download + silent install ────────────────────────────────────────────

procedure DownloadAndInstallJava();
var
  PSPath: String;
  Script: TArrayOfString;
  ExitCode: Integer;
begin
  PSPath := ExpandConstant('{tmp}\get_java.ps1');

  SetArrayLength(Script, 17);
  Script[0]  := '$ErrorActionPreference = "Stop"';
  Script[1]  := '$ProgressPreference = "SilentlyContinue"';
  Script[2]  := 'try {';
  Script[3]  := '  $a = Invoke-RestMethod "https://api.adoptium.net/v3/assets/latest/25/hotspot?architecture=x64&image_type=jre&os=windows&vendor=eclipse"';
  Script[4]  := '  $bin = $a[0].binary.installer';
  Script[5]  := '  $url = $bin.link';
  Script[6]  := '  $msi = "$env:TEMP\temurin-jre-25.msi"';
  Script[7]  := '  Invoke-WebRequest -Uri $url -OutFile $msi -UseBasicParsing';
  Script[8]  := '  $sum = $bin.checksum';
  Script[9]  := '  if ($sum) {';
  Script[10] := '    $expected = ($sum -replace "^sha256:","").ToUpper()';
  Script[11] := '    $got = (Get-FileHash $msi -Algorithm SHA256).Hash';
  Script[12] := '    if ($expected -ne $got) { Remove-Item $msi -Force; Write-Error "JRE checksum mismatch"; exit 2 }';
  Script[13] := '  }';
  Script[14] := '  Start-Process msiexec.exe -ArgumentList "/i `"$msi`" /qn REBOOT=ReallySuppress" -Wait';
  Script[15] := '  Remove-Item $msi -Force -ErrorAction SilentlyContinue';
  Script[16] := '} catch { Write-Error $_.Exception.Message; exit 1 }';

  SaveStringsToFile(PSPath, Script, False);

  WizardForm.StatusLabel.Caption :=
    'Завантаження та встановлення Java 25 (Eclipse Temurin JRE, ~70 МБ)...' + #13#10 +
    'Це може зайняти кілька хвилин.';
  WizardForm.StatusLabel.Update;

  Exec('powershell.exe',
       '-ExecutionPolicy Bypass -NonInteractive -File "' + PSPath + '"',
       '', SW_HIDE, ewWaitUntilTerminated, ExitCode);

  if ExitCode <> 0 then
    MsgBox(
      'Не вдалося автоматично встановити Java.' + #13#10 +
      'Завантажте та встановіть Java 25 вручну:' + #13#10 +
      'https://adoptium.net' + #13#10#13#10 +
      'Після встановлення Java програма запуститься нормально.',
      mbError, MB_OK);
end;

// ── Wizard hooks ──────────────────────────────────────────────────────────────

function InitializeSetup(): Boolean;
begin
  Result := True;
  if NeedJava() then
  begin
    if MsgBox(
      'Java 25 або новіша не знайдена на цьому комп''ютері.' + #13#10#13#10 +
      'Під час встановлення буде автоматично завантажено та' + #13#10 +
      'встановлено Java 25 JRE (~70 МБ). Потрібне підключення до інтернету.' + #13#10#13#10 +
      'Продовжити встановлення?',
      mbConfirmation, MB_YESNO) = IDNO then
      Result := False;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    if NeedJava() then
      DownloadAndInstallJava();
end;
