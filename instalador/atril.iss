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

[UninstallDelete]
; Lo que instaló uv (atril, su entorno y Python); la estación está fuera.
Type: filesandordirs; Name: "{app}\bin"
Type: filesandordirs; Name: "{app}\herramientas"
Type: filesandordirs; Name: "{app}\python"
Type: files; Name: "{app}\instalacion.log"

[Code]
function SetEnvironmentVariable(Name, Value: String): Boolean;
  external 'SetEnvironmentVariableW@kernel32.dll stdcall';

{ Variables de uv: todo dentro de la carpeta del programa, sin caché ni Python
  del sistema. }
procedure PrepareUv();
var
  App: String;
begin
  App := ExpandConstant('{app}');
  SetEnvironmentVariable('UV_TOOL_DIR', App + '\herramientas');
  SetEnvironmentVariable('UV_TOOL_BIN_DIR', App + '\bin');
  SetEnvironmentVariable('UV_PYTHON_INSTALL_DIR', App + '\python');
  SetEnvironmentVariable('UV_PYTHON_PREFERENCE', 'only-managed');
  SetEnvironmentVariable('UV_NO_CACHE', '1');
  SetEnvironmentVariable('UV_NO_MODIFY_PATH', '1');
end;

{ Instala (o actualiza) atril con uv; la salida queda en instalacion.log. }
function InstallAtril(): Boolean;
var
  Code: Integer;
  Command: String;
begin
  PrepareUv();
  Command := '/C ""' + ExpandConstant('{app}\uv.exe') + '" tool install --force'
    + ' --python {#PythonVersion} "atril=={#AppVersion}" > "'
    + ExpandConstant('{app}\instalacion.log') + '" 2>&1"';
  Result := Exec(ExpandConstant('{cmd}'), Command, ExpandConstant('{app}'),
    SW_HIDE, ewWaitUntilTerminated, Code) and (Code = 0);
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
