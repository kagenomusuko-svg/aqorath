; Aqorath Windows installer
; Requires Inno Setup

[Setup]
AppName=Aqorath
AppVersion=1.0
DefaultDirName={autopf}\Aqorath
DefaultGroupName=Aqorath
OutputBaseFilename=Aqorath-Setup
Compression=lzma
SolidCompression=yes

[Files]
Source: "..\dist\Aqorath\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{group}\Aqorath"; Filename: "{app}\Aqorath.exe"
Name: "{commondesktop}\Aqorath"; Filename: "{app}\Aqorath.exe"
