; CamDesk installer (Inno Setup 6). Built by:  .\scripts\build.ps1 -Installer
; Packs dist\CamDesk\ (the Nuitka folder build) into dist\CamDesk-Setup-<version>.exe.
;
; Installs per-user by default (no admin prompt) into %LOCALAPPDATA%\Programs\CamDesk;
; the user can pick "install for all users" in the wizard. Uninstall removes only the
; program files: settings (%APPDATA%\CamDesk) and footage (Videos\CamDesk) are the user's.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
; Never change AppId: Windows uses it to recognise upgrades and the uninstaller.
AppId={{FD286183-BE33-4B24-BDCE-8D31171AF872}
AppName=CamDesk
AppVersion={#AppVersion}
AppVerName=CamDesk {#AppVersion}
AppPublisher=DilshanRanabahu
AppPublisherURL=https://github.com/DilshanRanabahu/camdesk
AppSupportURL=https://github.com/DilshanRanabahu/camdesk/issues
VersionInfoVersion={#AppVersion}
VersionInfoDescription=CamDesk Setup
DefaultDirName={autopf}\CamDesk
DefaultGroupName=CamDesk
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=CamDesk-Setup-{#AppVersion}
SetupIconFile=..\src\camdesk\resources\app.ico
UninstallDisplayIcon={app}\CamDesk.exe
UninstallDisplayName=CamDesk
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
; Close a running CamDesk before replacing its files (upgrade / uninstall).
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\CamDesk\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\CamDesk"; Filename: "{app}\CamDesk.exe"
Name: "{autodesktop}\CamDesk"; Filename: "{app}\CamDesk.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\CamDesk.exe"; Description: "{cm:LaunchProgram,CamDesk}"; Flags: nowait postinstall skipifsilent
