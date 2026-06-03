; Inno Setup Script for AI Twitch Bot
#define MyAppName "AI Twitch Bot"
#define MyAppVersion "2.0.13"
#define MyAppPublisher "hannogeo"
#define MyAppURL "https://github.com/hannogeo/ai-twitch-bot"
#define MyAppExeName "AITwitchBot.exe"

[Setup]
AppId={{6E5F5F5F-5F5F-5F5F-5F5F-5F5F5F5F5F5F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
AllowNoIcons=yes
OutputDir=dist
OutputBaseFilename=AITwitchBot-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ChangesAssociations=no
SetupIconFile=app_icon.ico
UninstallDisplayIcon={app}\app_icon.ico
UninstallDisplayName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\AITwitchBot\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\AITwitchBot\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "version.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "bot_config.json"; DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist
Source: "ai_config.json"; DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"; Comment: "{#MyAppName}"
Name: "{autoprograms}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\app_icon.ico"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
