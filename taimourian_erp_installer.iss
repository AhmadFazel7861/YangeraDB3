; ─────────────────────────────────────────────────────────────────────────────
;  taimourian_erp_installer.iss  —  Inno Setup Script
;  قنادی تیموریان — Professional Installer
;  Designed by YangEra
;
;  HOW TO USE:
;    1. Open this file in Inno Setup Compiler
;    2. Press Ctrl+F9 to compile
;    3. Find the installer in the Output\ folder
; ─────────────────────────────────────────────────────────────────────────────

#define MyAppName      "سیستم مدیریت قنادی تیموریان "
#define MyAppNameEn    "YangEraDB"
#define MyAppVersion   "3.1.0"
#define MyAppPublisher "YangEra"
#define MyAppURL       ""
#define MyAppExeName   "YangEraDB.exe"
#define MyAppFolder    "YangEraDB"

; ── IMPORTANT: Change this path to where PyInstaller created the dist folder ──
#define DistFolder     "dist\YangEraDB"

[Setup]
; Basic app identity
AppId={{F3A2B1C4-9D8E-4F7A-B2C3-D4E5F6A7B8C9}
AppName={#MyAppNameEn}
AppVersion={#MyAppVersion}
AppVerName={#MyAppNameEn} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
AppCopyright=Copyright © 2024 YangEra

; Installation directory
DefaultDirName={autopf}\{#MyAppFolder}
DefaultGroupName={#MyAppNameEn}
DisableProgramGroupPage=yes
DisableDirPage=no

; Output installer file
OutputDir=Output
OutputBaseFilename=YangEraDB_Setup_v{#MyAppVersion}

; Compression (best for distribution)
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
LZMANumBlockThreads=4

; UI settings
WizardStyle=modern
WizardResizable=no
;WizardImageFile=compiler:WizModernImage-IS.bmp
;WizardSmallImageFile=compiler:WizModernSmallImage-IS.bmp

; Windows version requirement (Windows 10+)
MinVersion=10.0

; Privileges
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; 64-bit
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

; Uninstaller
Uninstallable=yes
UninstallDisplayName={#MyAppNameEn}
CreateUninstallRegKey=yes

; Allow running after install
DisableFinishedPage=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";     Description: "Create a &Desktop shortcut";           GroupDescription: "Additional shortcuts:"; Flags: checkedonce
Name: "startupicon";     Description: "Start automatically with &Windows";    GroupDescription: "Additional shortcuts:"; Flags: unchecked
Name: "quicklaunchicon"; Description: "Create a &Quick Launch shortcut";      GroupDescription: "Additional shortcuts:"; Flags: unchecked; OnlyBelowVersion: 6.1; Check: not IsAdminInstallMode

[Files]
; ── Copy entire PyInstaller dist folder ──────────────────────────────────────
Source: "{#DistFolder}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; ── If you have an icon file, copy it too ────────────────────────────────────
; Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start Menu shortcut
Name: "{group}\{#MyAppNameEn}";          Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#MyAppNameEn}"; Filename: "{uninstallexe}"

; Desktop shortcut
Name: "{autodesktop}\{#MyAppNameEn}";    Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

; Startup shortcut
Name: "{userstartup}\{#MyAppNameEn}";    Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: startupicon

[Registry]
; Register app in Windows Programs list
Root: HKCU; Subkey: "Software\{#MyAppPublisher}\{#MyAppNameEn}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey

[Run]
; Launch app after installation finishes
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppNameEn}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Nothing special needed — SQLite db stays in app folder

[UninstallDelete]
; Clean up generated files on uninstall (optional — comment out to keep user data)
; Type: filesandordirs; Name: "{app}\db.sqlite3"
; Type: filesandordirs; Name: "{app}\staticfiles"
; Type: filesandordirs; Name: "{app}\media"

[Messages]
; Customize installer messages
WelcomeLabel1=Welcome to the {#MyAppNameEn} Setup Wizard
WelcomeLabel2=This will install {#MyAppNameEn} version {#MyAppVersion} on your computer.%n%nDesigned by YangEra%n%nClick Next to continue.
FinishedHeadingLabel=Installation Complete
FinishedLabel={#MyAppNameEn} has been successfully installed.%n%nClick Finish to launch the application.%n%nDefault login:%n  Username: admin%n  Password: admin123
