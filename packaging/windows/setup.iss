#define AppName "Sankalp"
#define AppVersion "0.1.0"
#define AppPublisher "YantrAI"
#define RepoUrl "https://github.com/RSWAIN1486/sankalp"

[Setup]
AppId={{8D8A5D4A-C8E8-4E25-B5A8-C8B00D5BCDEA}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#RepoUrl}
DefaultDirName={%USERPROFILE}\.sankalp\installer
DefaultGroupName={#AppName}
DisableDirPage=yes
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=sankalp_setup_{#AppVersion}_x64
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest
WizardStyle=modern
ChangesEnvironment=yes
UninstallDisplayIcon={%USERPROFILE}\.sankalp\bin\sankalp.cmd
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\..\scripts\install_windows.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\scripts\install_windows.ps1"""; Flags: runhidden waituntilterminated

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{%USERPROFILE}\.sankalp\bin\sankalp.cmd"
Name: "{autodesktop}\{#AppName}"; Filename: "{%USERPROFILE}\.sankalp\bin\sankalp.cmd"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"
