; Inno Setup script. Build with:  iscc /DAppVersion=0.9.0 packaging\installer.iss
; Expects the PyInstaller output in dist\LanguageImmersionTools.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6F1B7C52-3E0D-4C8A-9A55-2D5B0F7A1E41}
AppName=Language Immersion Tools
AppVersion={#AppVersion}
AppPublisher=Language Immersion Tools
DefaultDirName={autopf}\Language Immersion Tools
DefaultGroupName=Language Immersion Tools
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=LanguageImmersionTools-Setup-{#AppVersion}
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\LanguageImmersionTools.exe
#ifexist "icon.ico"
SetupIconFile=icon.ico
#endif

[Files]
Source: "..\dist\LanguageImmersionTools\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Language Immersion Tools"; Filename: "{app}\LanguageImmersionTools.exe"
Name: "{autodesktop}\Language Immersion Tools"; Filename: "{app}\LanguageImmersionTools.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\LanguageImmersionTools.exe"; Description: "Launch Language Immersion Tools"; Flags: nowait postinstall skipifsilent
