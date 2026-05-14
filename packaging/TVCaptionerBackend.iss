#define AppName "TV Captioner Backend"
#define AppVersion "0.2"
#define AppPublisher "TV Captioner"
#define SourceDir "..\dist\TVCaptionerBackend"

[Setup]
AppId={{FDC4670A-D716-42A7-81F3-50F6EF7D67D9}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\TV Captioner Backend
DefaultGroupName=TV Captioner Backend
OutputBaseFilename=TVCaptionerBackendSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\TV Captioner Backend"; Filename: "{app}\TVCaptionerBackend.exe"
Name: "{commondesktop}\TV Captioner Backend"; Filename: "{app}\TVCaptionerBackend.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："

[Run]
Filename: "{app}\TVCaptionerBackend.exe"; Description: "启动 TV Captioner Backend"; Flags: nowait postinstall skipifsilent
