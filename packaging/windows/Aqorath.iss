#define MyAppName "Aqorath"
#define MyAppVersion "V1 Candidate"
#define MyAppPublisher "Aqorath"
#define MyAppExeName "Aqorath.exe"

[Setup]
AppId={{7B3E02A3-1E8D-4D2C-9CC2-04FA8712E23A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Aqorath
DefaultGroupName=Aqorath
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=output
OutputBaseFilename=Aqorath-Setup-V1-Candidate
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
UsePreviousAppDir=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Files]
Source: "build\Aqorath\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Aqorath"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\Aqorath"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir Aqorath"; Flags: nowait postinstall skipifsilent
