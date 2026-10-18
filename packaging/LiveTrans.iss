; Bộ cài LiveTrans — biên dịch bằng: ISCC.exe /DAppVersion=x.y.z packaging\LiveTrans.iss
; Cần chạy trước: packaging\gen_models_iss.py, packaging\make_icon.py, PyInstaller (xem build.ps1).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#include "build\models_defs.iss"

[Setup]
AppId={{8F3C2A51-7B4E-4C1D-9A6F-2E5B8D0C7A13}
AppName=LiveTrans
AppVersion={#AppVersion}
AppVerName=LiveTrans {#AppVersion}
AppPublisher=LiveTrans
DefaultDirName={autopf}\LiveTrans
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=LiveTrans-Setup-{#AppVersion}
SetupIconFile=build\LiveTrans.ico
UninstallDisplayIcon={app}\LiveTrans.exe
UninstallDisplayName=LiveTrans — Phiên dịch thời gian thực
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern dynamic
ExtraDiskSpaceRequired={#ModelsBytes}
AppMutex=Local\LiveTransSingleton
CloseApplications=no

[Languages]
Name: "vi"; MessagesFile: "compiler:Default.isl"

[Messages]
SetupWindowTitle=Cài đặt - %1
SetupAppRunningError=LiveTrans đang chạy.%n%nHãy thoát LiveTrans (chuột phải icon VI ở khay hệ thống → Thoát) rồi bấm OK, hoặc bấm Cancel để huỷ.
UninstallAppRunningError=LiveTrans đang chạy.%n%nHãy thoát LiveTrans (chuột phải icon VI ở khay hệ thống → Thoát) rồi bấm OK, hoặc bấm Cancel để huỷ.
ExitSetupTitle=Thoát cài đặt
ExitSetupMessage=Cài đặt chưa xong. Nếu thoát bây giờ, LiveTrans sẽ không được cài.%n%nThoát cài đặt?
ButtonBack=< &Quay lại
ButtonNext=&Tiếp >
ButtonInstall=&Cài đặt
ButtonCancel=Huỷ
ButtonFinish=&Hoàn tất
ButtonBrowse=&Chọn...
ButtonStopDownload=&Dừng tải
WelcomeLabel1=Chào mừng đến với trình cài đặt [name]
WelcomeLabel2=Trình cài đặt sẽ cài [name/ver] lên máy của bạn.%n%nTrong quá trình cài, model AI (nhận dạng giọng nói và dịch, 0,8–2 GB tuỳ chất lượng bạn chọn) sẽ được tải từ Internet. Sau đó LiveTrans chạy hoàn toàn offline.
WizardSelectDir=Chọn thư mục cài đặt
SelectDirDesc=Cài [name] vào đâu?
SelectDirLabel3=[name] sẽ được cài vào thư mục sau.
SelectDirBrowseLabel=Bấm Tiếp để tiếp tục. Muốn chọn thư mục khác, bấm Chọn.
DiskSpaceGBLabel=Cần ít nhất [gb] GB dung lượng trống.
DiskSpaceMBLabel=Cần ít nhất [mb] MB dung lượng trống.
WizardSelectTasks=Tuỳ chọn thêm
SelectTasksDesc=Bạn muốn trình cài đặt làm thêm gì?
SelectTasksLabel2=Chọn các tuỳ chọn cho [name], rồi bấm Tiếp.
WizardReady=Sẵn sàng cài đặt
ReadyLabel1=Trình cài đặt đã sẵn sàng tải model và cài [name].
ReadyLabel2a=Bấm Cài đặt để bắt đầu, hoặc Quay lại để xem/sửa lựa chọn.
ReadyLabel2b=Bấm Cài đặt để bắt đầu.
ReadyMemoDir=Thư mục cài đặt:
ReadyMemoTasks=Tuỳ chọn thêm:
DownloadingLabel2=Đang tải model…
StopDownload=Bạn có chắc muốn dừng tải?
ErrorDownloadAborted=Đã dừng tải
ErrorDownloadFailed=Tải thất bại: %1 %2
ErrorDownloadSizeFailed=Không lấy được dung lượng file: %1 %2
ErrorDownloading=Có lỗi khi tải file:
WizardInstalling=Đang cài đặt
InstallingLabel=Vui lòng chờ trong khi [name] được cài lên máy.
StatusExtractFiles=Đang giải nén…
StatusCreateIcons=Đang tạo shortcut…
StatusRunProgram=Đang hoàn tất…
StatusRollback=Đang hoàn tác…
FinishedHeadingLabel=Đã cài xong [name]
FinishedLabelNoIcons=[name] đã được cài lên máy.
FinishedLabel=[name] đã được cài lên máy. Mở từ shortcut LiveTrans trên Desktop hoặc Start Menu: cửa sổ LiveTrans có nút Bắt đầu/Dừng dịch, ô gõ Việt → Anh và Cài đặt.
ClickFinish=Bấm Hoàn tất để đóng trình cài đặt.
RunEntryExec=Chạy %1 ngay
AdditionalIcons=Shortcut:
CreateDesktopIcon=Tạo shortcut ngoài &Desktop
ConfirmUninstall=Bạn có chắc muốn gỡ hoàn toàn %1 (kèm model đã tải)?
UninstallStatusLabel=Đang gỡ %1 khỏi máy…
UninstalledAll=Đã gỡ %1 khỏi máy.
WizardUninstalling=Đang gỡ cài đặt

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startup"; Description: "Tự chạy LiveTrans khi khởi động Windows"; GroupDescription: "Khởi động:"; Flags: unchecked

[Files]
Source: "build\dist\LiveTrans\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Model tải trong lúc cài (trang tải ở bước Sẵn sàng) — bỏ qua nếu đã có sẵn từ lần cài trước
#include "build\models_files.iss"

[Icons]
Name: "{autoprograms}\LiveTrans"; Filename: "{app}\LiveTrans.exe"
Name: "{autodesktop}\LiveTrans"; Filename: "{app}\LiveTrans.exe"; Tasks: desktopicon

[Registry]
; Cùng khoá với livetrans/autostart.py (ô "Tự chạy khi khởi động Windows" trong tab Cài đặt)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "LiveTrans"; \
  ValueData: """{app}\LiveTrans.exe"" --minimized"; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\LiveTrans.exe"; Description: "{cm:LaunchProgram,LiveTrans}"; Flags: nowait postinstall skipifsilent

[CustomMessages]
LaunchProgram=Chạy %1 ngay

[UninstallDelete]
Type: filesandordirs; Name: "{app}\models"
Type: files; Name: "{app}\install_profile.json"
Type: filesandordirs; Name: "{localappdata}\LiveTrans\logs"

[Code]
type
  TMemoryStatusEx = record
    dwLength: DWORD;
    dwMemoryLoad: DWORD;
    ullTotalPhys: Int64;
    ullAvailPhys: Int64;
    ullTotalPageFile: Int64;
    ullAvailPageFile: Int64;
    ullTotalVirtual: Int64;
    ullAvailVirtual: Int64;
    ullAvailExtendedVirtual: Int64;
  end;

function GlobalMemoryStatusEx(var lpBuffer: TMemoryStatusEx): BOOL;
  external 'GlobalMemoryStatusEx@kernel32.dll stdcall';

var
  DownloadPage: TDownloadWizardPage;
  QualityPage: TInputOptionWizardPage;
  PendingDownloads: Integer;

function TotalRamMB: Int64;
var
  Status: TMemoryStatusEx;
begin
  Status.dwLength := 64;
  if GlobalMemoryStatusEx(Status) then
    Result := Status.ullTotalPhys div (1024 * 1024)
  else
    Result := 8192;
end;

{ Cùng quy tắc với livetrans.models.recommend_profile: 0 = chính xác, 1 = cân bằng, 2 = nhanh }
function RecommendedQuality: Integer;
var
  Cpus: Integer;
  RamMB: Int64;
begin
  Cpus := StrToIntDef(GetEnv('NUMBER_OF_PROCESSORS'), 4);
  RamMB := TotalRamMB;
  if (Cpus >= 6) and (RamMB >= 7680) then
    Result := 0
  else if (Cpus >= 4) and (RamMB >= 5632) then
    Result := 1
  else
    Result := 2;
end;

function SelectedProfile: String;
begin
  case QualityPage.SelectedValueIndex of
    0: Result := 'accurate';
    1: Result := 'balanced';
  else
    Result := 'fast';
  end;
end;

function ProfileLetter: String;
begin
  case QualityPage.SelectedValueIndex of
    0: Result := 'a';
    1: Result := 'b';
  else
    Result := 'f';
  end;
end;

procedure AddModelFile(const Url, TmpName, RelPath, Sha256, Profiles: String);
begin
  if Pos(ProfileLetter, Profiles) = 0 then
    Exit;
  if FileExists(ExpandConstant('{app}\models\' + RelPath)) then
    Log('Đã có ' + RelPath + ', bỏ qua')
  else begin
    DownloadPage.Add(Url, TmpName, Sha256);
    PendingDownloads := PendingDownloads + 1;
  end;
end;

#include "build\models_code.iss"

procedure InitializeWizard;
var
  Rec: Integer;
begin
  QualityPage := CreateInputOptionPage(wpSelectDir, 'Chất lượng dịch',
    'Chọn mức phù hợp với máy của bạn',
    Format('Máy này có %s luồng CPU và %d GB RAM. Có thể đổi lại bất cứ lúc nào trong menu khay ' +
      '(chuột phải icon VI → Chất lượng dịch).', [GetEnv('NUMBER_OF_PROCESSORS'), (TotalRamMB + 512) div 1024]),
    True, False);
  QualityPage.Add('Chính xác nhất — Whisper small + NLLB 1.3B (tải {#Size_accurate} GB; CPU ≥ 6 luồng, RAM ≥ 8 GB)');
  QualityPage.Add('Cân bằng — Whisper small + NLLB 600M (tải {#Size_balanced} GB)');
  QualityPage.Add('Nhanh — Whisper base + NLLB 600M (tải {#Size_fast} GB; cho máy yếu)');
  Rec := RecommendedQuality;
  QualityPage.CheckListBox.ItemCaption[Rec] := QualityPage.CheckListBox.ItemCaption[Rec] + '   ★ đề xuất cho máy này';
  QualityPage.SelectedValueIndex := Rec;

  DownloadPage := CreateDownloadPage('Đang tải model AI',
    'Đang tải model nhận dạng giọng nói và dịch. Thời gian tuỳ tốc độ mạng.', nil);
  DownloadPage.ShowBaseNameInsteadOfUrl := True;
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo,
  MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
begin
  Result := MemoDirInfo + NewLine + NewLine +
    'Chất lượng dịch:' + NewLine + Space + QualityPage.CheckListBox.ItemCaption[QualityPage.SelectedValueIndex];
  if MemoTasksInfo <> '' then
    Result := Result + NewLine + NewLine + MemoTasksInfo;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    SaveStringToFile(ExpandConstant('{app}\install_profile.json'),
      '{"quality": "' + SelectedProfile + '"}', False);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Error: String;
begin
  Result := True;
  if CurPageID <> wpReady then
    Exit;
  DownloadPage.Clear;
  PendingDownloads := 0;
  AddAllModelFiles;
  if PendingDownloads = 0 then
    Exit;
  DownloadPage.Show;
  try
    try
      DownloadPage.Download;
    except
      if DownloadPage.AbortedByUser then
        Error := 'Bạn đã dừng tải model.'
      else
        Error := Format('Không tải được model (%s): %s', [DownloadPage.LastBaseNameOrUrl, GetExceptionMessage]);
      Result := SuppressibleMsgBox(Error + #13#10#13#10 +
        'Vẫn tiếp tục cài đặt? LiveTrans sẽ tự tải model khi chạy lần đầu (cần Internet).' + #13#10 +
        'Chọn No để quay lại và thử tải lại.',
        mbConfirmation, MB_YESNO, IDYES) = IDYES;
    end;
  finally
    DownloadPage.Hide;
  end;
end;
