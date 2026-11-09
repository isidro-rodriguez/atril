; Instalador de atril para Windows (Inno Setup 6), por usuario y sin administrador.
;
; Lleva uv.exe y el icono. Al instalar, uv instala atril (y un Python propio) dentro
; de la carpeta del programa, así que desinstalar solo borra esa carpeta: nunca la
; estación, las copias ni ATRIL_ESTACION. Lo construye la CI (publish.yml):
;   iscc /DAppVersion=X.Y.Z /DSourceDir=<carpeta con uv.exe> instalador\atril.iss

#ifndef AppVersion
  #error Falta /DAppVersion=X.Y.Z
#endif
#ifndef SourceDir
  #define SourceDir "."
#endif
#define AppName "Atril"
#define PythonVersion "3.13"

[Setup]
AppId={{7C2F4E7A-5B8D-4E54-9A51-3F2C8B6D1A90}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Isidro Rodríguez
AppPublisherURL=https://github.com/isidro-rodriguez/atril
AppSupportURL=https://github.com/isidro-rodriguez/atril/issues
DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ChangesEnvironment=yes
; La ventana de atril crea este mutex: instalar o desinstalar con atril abierto
; pide cerrarlo primero (sus ficheros estarían en uso).
AppMutex=AtrilGui
; Sin RedirectionGuard: Inno Setup lo activa por defecto y sus procesos hijos lo
; heredan (también los de ExecAsOriginalUser sin elevación), y uv no puede usar el
; enlace (junction) de versión menor de Python que crea (os error 448). Protege a
; procesos elevados de enlaces de usuarios sin privilegios: aquí Setup corre como
; el propio usuario, sin elevar, así que no hay frontera de privilegios que guardar.
RedirectionGuard=no
SetupIconFile=..\src\atril\gui\recursos\atril.ico
UninstallDisplayIcon={app}\atril.ico
UninstallDisplayName={#AppName}
OutputDir=..\dist
OutputBaseFilename=atril-{#AppVersion}-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el escritorio"; Flags: unchecked

[Files]
Source: "{#SourceDir}\uv.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\src\atril\gui\recursos\atril.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion

[Icons]
; AppUserModelID igual que el de la ventana: Windows agrupa ventana y acceso
; directo y pone «Atril» en las notificaciones.
Name: "{userprograms}\{#AppName}"; Filename: "{app}\bin\atril-gui.exe"; \
  IconFilename: "{app}\atril.ico"; AppUserModelID: "atril.gui"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\bin\atril-gui.exe"; \
  IconFilename: "{app}\atril.ico"; AppUserModelID: "atril.gui"; Tasks: escritorio

[Run]
Filename: "{app}\bin\atril-gui.exe"; Description: "Abrir Atril"; \
  Flags: nowait postinstall skipifsilent
; Actualización desde la ventana (/SILENT /abrir=si): la vuelve a abrir al acabar.
Filename: "{app}\bin\atril-gui.exe"; Flags: nowait; Check: ReopenAfterUpdate

[UninstallDelete]
; Lo que instaló uv (atril, su entorno y Python); la estación está fuera.
Type: filesandordirs; Name: "{app}\bin"
Type: filesandordirs; Name: "{app}\herramientas"
Type: filesandordirs; Name: "{app}\python"
Type: files; Name: "{app}\instalacion.log"

[Code]
{ Variables de uv: todo dentro de la carpeta del programa, sin caché ni Python
  del sistema. }
function UvEnvironment(): String;
var
  App: String;
begin
  App := ExpandConstant('{app}');
  Result := 'set "UV_TOOL_DIR=' + App + '\herramientas"&& '
    + 'set "UV_TOOL_BIN_DIR=' + App + '\bin"&& '
    + 'set "UV_PYTHON_INSTALL_DIR=' + App + '\python"&& '
    + 'set "UV_PYTHON_PREFERENCE=only-managed"&& '
    + 'set "UV_NO_CACHE=1"&& '
    + 'set "UV_NO_MODIFY_PATH=1"&& ';
end;

function OpenProcess(Access: DWORD; Inherit: BOOL; Pid: DWORD): THandle;
  external 'OpenProcess@kernel32.dll stdcall';
function WaitForSingleObject(Handle: THandle; Milliseconds: DWORD): DWORD;
  external 'WaitForSingleObject@kernel32.dll stdcall';
function CloseHandle(Handle: THandle): BOOL;
  external 'CloseHandle@kernel32.dll stdcall';

{ Actualización desde la ventana (/esperar=<pid>): espera a que esa ventana se
  cierre del todo. Mientras su Python siga vivo, sus ficheros del entorno están en
  uso y uv no puede sustituirlos. }
function InitializeSetup(): Boolean;
var
  Pid: Integer;
  Handle: THandle;
begin
  Pid := StrToIntDef(ExpandConstant('{param:esperar|0}'), 0);
  if Pid > 0 then
  begin
    Handle := OpenProcess($00100000, False, Pid);  { SYNCHRONIZE }
    if Handle <> 0 then
    begin
      WaitForSingleObject(Handle, 60000);
      CloseHandle(Handle);
    end;
  end;
  Result := True;
end;

{ Instala (o actualiza) atril con uv; la salida queda en instalacion.log.
  Va por cmd para poner las variables de uv y redirigir la salida. }
function InstallAtril(): Boolean;
var
  Code, Attempt: Integer;
  Command: String;
begin
  Command := '/S /C "' + UvEnvironment() + '"' + ExpandConstant('{app}\uv.exe')
    + '" tool install --force --python {#PythonVersion} "atril=={#AppVersion}" > "'
    + ExpandConstant('{app}\instalacion.log') + '" 2>&1"';
  { Unos reintentos: un antivirus o un proceso que acaba de cerrarse pueden
    retener un fichero del entorno unos segundos. }
  for Attempt := 1 to 3 do
  begin
    Result := Exec(ExpandConstant('{cmd}'), Command,
      ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, Code) and (Code = 0);
    if Result then
      exit;
    Sleep(5000);
  end;
end;

function ReopenAfterUpdate(): Boolean;
begin
  Result := WizardSilent and (ExpandConstant('{param:abrir|no}') = 'si');
end;

function PathEntry(): String;
begin
  Result := ExpandConstant('{app}\bin');
end;

function UserPath(): String;
begin
  if not RegQueryStringValue(HKCU, 'Environment', 'Path', Result) then
    Result := '';
end;

{ La CLI (atril) en el PATH del usuario, al final: no tapa otra instalación. }
procedure AddToPath();
var
  Path: String;
begin
  Path := UserPath();
  if Pos(';' + Uppercase(PathEntry()) + ';', ';' + Uppercase(Path) + ';') > 0 then
    exit;
  if (Path <> '') and (Copy(Path, Length(Path), 1) <> ';') then
    Path := Path + ';';
  RegWriteExpandStringValue(HKCU, 'Environment', 'Path', Path + PathEntry());
end;

procedure RemoveFromPath();
var
  Path: String;
  Start: Integer;
begin
  Path := ';' + UserPath() + ';';
  Start := Pos(';' + Uppercase(PathEntry()) + ';', Uppercase(Path));
  if Start = 0 then
    exit;
  Delete(Path, Start, Length(PathEntry()) + 1);
  RegWriteExpandStringValue(HKCU, 'Environment', 'Path', Copy(Path, 2, Length(Path) - 2));
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    WizardForm.StatusLabel.Caption :=
      'Instalando atril y Python (descarga unos 50 MB, puede tardar)...';
    if not InstallAtril() then
      RaiseException('No se ha podido instalar atril. Comprueba la conexión a '
        + 'Internet y vuelve a ejecutar el instalador. Detalle en '
        + ExpandConstant('{app}\instalacion.log'));
    AddToPath();
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RemoveFromPath();
end;
