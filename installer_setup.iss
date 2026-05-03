; Inno Setup 安装脚本 - 短视频生成器
; 功能: 自动检测系统,安装Python环境,部署程序

#define MyAppName "短视频生成器"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "liudaba"
#define MyAppURL "https://github.com/liudaba/Image-Video-Editor"
#define MyAppExeName "短视频生成器.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=LICENSE
OutputDir=installer_output
OutputBaseFilename=短视频生成器_Setup_v{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1; Check: not IsAdminInstallMode

[Files]
; 主程序文件
Source: "dist\短视频生成器\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "assets\icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: quicklaunchicon

[Run]
; 首次运行时检查并安装依赖
Filename: "{app}\check_and_install_deps.bat"; Description: "检查并安装运行环境"; Flags: postinstall skipifsilent

[Code]
var
  DownloadPage: TDownloadWizardPage;

function OnDownloadProgress(const Url, FileName: String; const Progress, ProgressMax: Int64): Boolean;
begin
  if Progress = ProgressMax then
    Log(Format('Successfully downloaded file to {tmp}: %s', [FileName]));
  Result := True;
end;

procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage(SetupMessage(msgWizardPreparing), SetupMessage(msgPreparingDesc), @OnDownloadProgress);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  PythonInstalled: Boolean;
  ResultCode: Integer;
begin
  Result := True;
  
  if CurPageID = wpReady then
  begin
    // 检查Python是否已安装
    PythonInstalled := RegKeyExists(HKLM, 'SOFTWARE\Python\PythonCore\3.10\InstallPath') or
                       RegKeyExists(HKLM, 'SOFTWARE\Python\PythonCore\3.11\InstallPath');
    
    if not PythonInstalled then
    begin
      if MsgBox('检测到您的系统未安装Python 3.10+,是否需要自动下载安装?', mbConfirmation, MB_YESNO) = IDYES then
      begin
        DownloadPage.Clear;
        DownloadPage.Add('https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe', 'python-3.11.9-amd64.exe', '');
        DownloadPage.Show;
        
        try
          DownloadPage.Download;
          
          // 安装Python
          Exec(ExpandConstant('{tmp}\python-3.11.9-amd64.exe'), '/quiet InstallAllUsers=1 PrependPath=1', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
          
          if ResultCode <> 0 then
          begin
            MsgBox('Python安装失败,请手动安装Python 3.10+', mbError, MB_OK);
            Result := False;
          end;
        except
          MsgBox('Python下载失败,请检查网络连接', mbError, MB_OK);
          Result := False;
        end;
        
        DownloadPage.Hide;
      end;
    end;
  end;
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  
  // 检查系统架构
  if not IsWin64 then
  begin
    MsgBox('本软件仅支持64位Windows系统', mbError, MB_OK);
    Result := False;
  end;
  
  // 检查Windows版本
  if GetWindowsVersion < EncodeVer(10, 0, 0, 0) then
  begin
    MsgBox('本软件需要Windows 10或更高版本', mbError, MB_OK);
    Result := False;
  end;
end;
