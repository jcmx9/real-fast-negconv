# Installer for real-fast-negconv (rfnegconv) on Windows (PowerShell 5.1+).
#
#   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/jcmx9/real-fast-negconv/main/install.ps1 | iex"
#   powershell -ExecutionPolicy ByPass -c "& ([scriptblock]::Create((irm https://raw.githubusercontent.com/jcmx9/real-fast-negconv/main/install.ps1))) -OhneDienst"
#   powershell -ExecutionPolicy ByPass -c "& ([scriptblock]::Create((irm https://raw.githubusercontent.com/jcmx9/real-fast-negconv/main/install.ps1))) -Uninstall"
#
# Besides the background service it creates the Start menu entry "Negative
# entwickeln" that processes the Negative folder once and shows the result.
# -OhneDienst installs no service (an existing one is removed); a run without
# it installs the service again.
#
# Running it again updates the program. Existing config, folders and images
# are never changed or deleted. No admin rights needed.
#
# Environment (tests/CI):
#   RFNEGCONV_SOURCE        local path or uv source spec instead of the release
#   RFNEGCONV_NO_SERVICE=1  do not install/remove the background service
#   RFNEGCONV_PICTURES_DIR  base folder instead of the Pictures folder
#   RFNEGCONV_DESKTOP_DIR   folder for the shortcuts instead of the Desktop
#   RFNEGCONV_START_MENU_DIR  folder for "Negative entwickeln" instead of the Start menu
#   RFNEGCONV_EXIFTOOL_SITE   download site for exiftool instead of exiftool.org
#
# The file is kept ASCII-only (umlauts via [char]) so it parses identically
# via "irm | iex", -File and in Windows PowerShell 5.1 without a BOM.
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSAvoidUsingWriteHost', '', Justification = 'Interactive installer output for the user.')]
[CmdletBinding()]
param(
    [switch]$Uninstall,
    [switch]$OhneDienst
)

# "irm | iex" runs in the caller's scope: keep its preferences and restore them at the end.
$script:CallerErrorAction = $ErrorActionPreference
$script:CallerProgress = $ProgressPreference
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'  # Invoke-WebRequest is very slow with progress in 5.1

$script:Version = '26.10.7'
$script:AppName = 'real-fast-negconv'
$script:RepoUrl = 'https://github.com/jcmx9/real-fast-negconv'
$script:RawUrl = 'https://raw.githubusercontent.com/jcmx9/real-fast-negconv'
$script:ExifToolSite = 'https://exiftool.org'
if ($env:RFNEGCONV_EXIFTOOL_SITE) { $script:ExifToolSite = $env:RFNEGCONV_EXIFTOOL_SITE }
$script:ExifToolMirror = 'https://sourceforge.net/projects/exiftool/files'  # linked from exiftool.org
$script:UserAgent = 'rfnegconv-installer'  # a browser-like agent gets an HTML page from the mirror

$script:ae = [char]0x00E4
$script:oe = [char]0x00F6
$script:ue = [char]0x00FC
$script:lq = [char]0x201E
$script:rq = [char]0x201C
$script:Check = [char]0x2713
$script:Arrow = [char]0x2192

$script:DataDir = $null
$script:StateFile = $null
$script:ExifToolDir = $null
$script:ExifToolExe = $null
$script:Uv = $null
$script:Folders = @{}
$script:WithoutService = [bool]$OhneDienst
$script:LauncherName = 'Negative entwickeln'
$script:LauncherPlace = ''
$script:ServiceRemoved = $false
$script:ManualRunActive = $false

function Get-UserFolder {
    # The folder's path even if it does not exist (yet), as platformdirs reads
    # it (SHGetKnownFolderPath with KF_FLAG_DONT_VERIFY). Plain GetFolderPath
    # returns an empty string for a missing folder, e.g. AppData\Local of a
    # fresh profile.
    param([Environment+SpecialFolder]$Folder)
    return [Environment]::GetFolderPath($Folder, [Environment+SpecialFolderOption]::DoNotVerify)
}

function Initialize-InstallerPath {
    if (-not $env:USERPROFILE -or -not $env:LOCALAPPDATA -or -not (Get-UserFolder -Folder 'LocalApplicationData')) {
        Write-Host "Fehler: Der Benutzerordner (USERPROFILE/LOCALAPPDATA) ist nicht gesetzt. Bitte als normaler Benutzer in PowerShell ausf$($script:ue)hren." -ForegroundColor Red
        throw 'rfnegconv: USERPROFILE or LOCALAPPDATA is empty - installation aborted.'
    }
    $script:DataDir = Join-Path -Path (Get-UserFolder -Folder 'LocalApplicationData') -ChildPath $script:AppName
    $script:StateFile = Join-Path -Path $script:DataDir -ChildPath 'installer-state'
    $script:ExifToolDir = Join-Path -Path $script:DataDir -ChildPath 'exiftool'
    $script:ExifToolExe = Join-Path -Path $script:ExifToolDir -ChildPath 'exiftool.exe'
}

function Write-Info {
    param([string]$Message)
    Write-Host $Message
}

function Write-Hint {
    param([string]$Message)
    Write-Host "Hinweis: $Message" -ForegroundColor Yellow
}

function Write-Failure {
    param([string]$Message)
    Write-Host "Fehler: $Message" -ForegroundColor Red
    throw 'rfnegconv: Installation abgebrochen.'
}

# --- state file: which parts this installer set up itself -------------------

function Read-State {
    param([string]$Key)
    if (-not (Test-Path -LiteralPath $script:StateFile)) { return '' }
    foreach ($line in Get-Content -LiteralPath $script:StateFile -Encoding UTF8) {
        if ($line.StartsWith("$Key=")) { return $line.Substring($Key.Length + 1) }
    }
    return ''
}

function Write-State {
    param([string]$Key, [string]$Value)
    New-Item -ItemType Directory -Force -Path $script:DataDir | Out-Null
    $lines = @()
    if (Test-Path -LiteralPath $script:StateFile) {
        $lines = @(Get-Content -LiteralPath $script:StateFile -Encoding UTF8 | Where-Object { -not $_.StartsWith("$Key=") })
    }
    $lines += "$Key=$Value"
    Set-Content -LiteralPath $script:StateFile -Value $lines -Encoding UTF8
}

function Clear-StateKey {
    param([string]$Key)
    if (-not (Test-Path -LiteralPath $script:StateFile)) { return }
    $lines = @(Get-Content -LiteralPath $script:StateFile -Encoding UTF8 | Where-Object { -not $_.StartsWith("$Key=") })
    Set-Content -LiteralPath $script:StateFile -Value $lines -Encoding UTF8
}

# --- helpers ----------------------------------------------------------------

function Invoke-Tool {
    # Runs a native program without turning its stderr into terminating errors.
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$ArgumentList = @(),
        [switch]$Capture
    )
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        if ($Capture) {
            $output = @(& $FilePath @ArgumentList)
        }
        else {
            & $FilePath @ArgumentList | Out-Host
            $output = @()
        }
        return [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = $output }
    }
    finally {
        $ErrorActionPreference = $previous
    }
}

function Get-Download {
    # HTTPS only: the start URL and the final URL after redirects. A host
    # that does not answer fails after TimeoutSec instead of hanging.
    param([string]$Uri, [string]$OutFile, [int]$TimeoutSec = 30)
    if (-not $Uri.StartsWith('https://')) { throw "refusing non-https download: $Uri" }
    $response = Invoke-WebRequest -Uri $Uri -OutFile $OutFile -UseBasicParsing -UserAgent $script:UserAgent -MaximumRedirection 10 -TimeoutSec $TimeoutSec -PassThru
    $final = $null
    $base = $response.BaseResponse
    if ($null -ne $base.ResponseUri) { $final = $base.ResponseUri }  # Windows PowerShell 5.1
    elseif ($null -ne $base.RequestMessage) { $final = $base.RequestMessage.RequestUri }  # PowerShell 7
    if ($null -ne $final -and $final.Scheme -ne 'https') {
        Remove-Item -LiteralPath $OutFile -Force -ErrorAction SilentlyContinue
        throw "refusing download redirected to $($final.Scheme): $Uri"
    }
}

function Add-ToPath {
    param([string]$Directory)
    if ($Directory -and (Test-Path -LiteralPath $Directory)) {
        $env:Path = "$Directory;$env:Path"
    }
}

function Find-Uv {
    $command = Get-Command -Name 'uv' -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -ne $command) {
        $script:Uv = $command.Source
        return $true
    }
    $candidates = @($env:XDG_BIN_HOME)
    foreach ($root in @($env:USERPROFILE, $HOME)) {
        if ($root) { $candidates += @((Join-Path -Path $root -ChildPath '.local\bin'), (Join-Path -Path $root -ChildPath '.cargo\bin')) }
    }
    foreach ($dir in $candidates) {
        if (-not $dir) { continue }
        $exe = Join-Path -Path $dir -ChildPath 'uv.exe'
        if (Test-Path -LiteralPath $exe) {
            Add-ToPath -Directory $dir
            $script:Uv = $exe
            return $true
        }
    }
    return $false
}

function Add-ToolBinToPath {
    $result = Invoke-Tool -FilePath $script:Uv -ArgumentList @('tool', 'dir', '--bin') -Capture
    if ($result.ExitCode -eq 0 -and $result.Output.Count -gt 0) {
        Add-ToPath -Directory ([string]$result.Output[0]).Trim()
    }
}

function Test-ToolInstalled {
    param([string]$Name)
    $result = Invoke-Tool -FilePath $script:Uv -ArgumentList @('tool', 'list') -Capture
    foreach ($line in $result.Output) {
        if ("$line".StartsWith("$Name ")) { return $true }
    }
    return $false
}

function Find-App {
    $command = Get-Command -Name 'rfnegconv' -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $command) { return $null }
    return $command.Source
}

function Close-RunningApp {
    # A running program locks its files; stop it right before the uv step that
    # replaces or removes this tool. Returns $true if a process was stopped.
    # -WatcherOnly (update): only the background watcher ("rfnegconv -Q watch")
    # is stopped; a manual run (e.g. "Negative entwickeln") is never
    # interrupted and only sets $script:ManualRunActive.
    param([Parameter(Mandatory = $true)][string]$Tool, [switch]$WatcherOnly)
    $stopped = $false
    $toolDir = ''
    if ($script:Uv) {
        $result = Invoke-Tool -FilePath $script:Uv -ArgumentList @('tool', 'dir') -Capture
        if ($result.ExitCode -eq 0 -and $result.Output.Count -gt 0) {
            $toolDir = ([string]$result.Output[0]).Trim()
        }
    }
    $processes = @()
    try {
        $processes = @(Get-CimInstance -ClassName Win32_Process -ErrorAction Stop | ForEach-Object {
                [pscustomobject]@{ Id = $_.ProcessId; Name = [string]$_.Name; Path = [string]$_.ExecutablePath; CommandLine = [string]$_.CommandLine }
            })
    }
    catch {
        Write-Verbose "process list unavailable: $_"
        if (-not $WatcherOnly) {
            # without command lines a watcher cannot be told apart; removal stops all
            $processes = @(Get-Process -ErrorAction SilentlyContinue | ForEach-Object {
                    $exePath = ''
                    try { $exePath = [string]$_.Path } catch { $exePath = '' }
                    [pscustomobject]@{ Id = $_.Id; Name = "$($_.ProcessName).exe"; Path = $exePath; CommandLine = '' }
                })
        }
    }
    foreach ($process in $processes) {
        $path = $process.Path
        $isApp = $process.Name -eq 'rfnegconv.exe'
        $inTool = $toolDir -and $path -and
            $path.StartsWith((Join-Path -Path $toolDir -ChildPath $Tool) + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)
        if (-not ($isApp -or $inTool)) { continue }
        if ($WatcherOnly -and $process.CommandLine -notmatch '\swatch("|\s|$)') {
            $script:ManualRunActive = $true
            continue
        }
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        $stopped = $true
    }
    return $stopped
}

# --- install steps ----------------------------------------------------------

function Install-Uv {
    if (Find-Uv) {
        Write-Info "$script:Check uv ist schon da."
        return
    }
    Write-Info "$script:Arrow Installiere uv (Programm-Verwaltung) ..."
    $installer = Join-Path -Path ([IO.Path]::GetTempPath()) -ChildPath 'rfnegconv-uv-install.ps1'
    try {
        Get-Download -Uri 'https://astral.sh/uv/install.ps1' -OutFile $installer
    }
    catch {
        Write-Failure "uv konnte nicht geladen werden. Bitte Internetverbindung pr$($script:ue)fen."
    }
    $result = Invoke-Tool -FilePath 'powershell' -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $installer)
    Remove-Item -LiteralPath $installer -Force -ErrorAction SilentlyContinue
    if ($result.ExitCode -ne 0) { Write-Failure 'uv konnte nicht installiert werden.' }
    if (-not (Find-Uv)) { Write-Failure 'uv wurde installiert, ist aber nicht auffindbar.' }
    Write-State -Key 'uv' -Value $script:Uv
    Write-Info "$script:Check uv installiert."
}

function Install-App {
    Write-Info "$script:Arrow Installiere rfnegconv $script:Version (das kann ein paar Minuten dauern) ..."
    # the library versions fixed for this release (constraints.txt, exported
    # from uv.lock): every install of a version gets the same libraries
    $extra = @()
    $constraints = $null
    if ($env:RFNEGCONV_SOURCE) {
        if (Test-Path -LiteralPath $env:RFNEGCONV_SOURCE -PathType Container) {
            $spec = (Resolve-Path -LiteralPath $env:RFNEGCONV_SOURCE).Path
            $extra = @('--reinstall-package', $script:AppName)
            $local = Join-Path -Path $spec -ChildPath 'constraints.txt'
            if (Test-Path -LiteralPath $local) { $extra += @('--constraints', $local) }
        }
        else {
            $spec = $env:RFNEGCONV_SOURCE
        }
    }
    else {
        $spec = "$script:AppName @ $script:RepoUrl/archive/refs/tags/v$script:Version.tar.gz"
        $constraints = Join-Path -Path ([IO.Path]::GetTempPath()) -ChildPath ('rfnegconv-constraints-' + [guid]::NewGuid().ToString('N') + '.txt')
        try {
            Get-Download -Uri "$script:RawUrl/v$script:Version/constraints.txt" -OutFile $constraints
        }
        catch {
            Remove-Item -LiteralPath $constraints -Force -ErrorAction SilentlyContinue
            $status = 0
            try { $status = [int]$_.Exception.Response.StatusCode } catch { $status = 0 }
            if ($status -eq 404) {
                Write-Failure "Version $script:Version wurde auf dem Server nicht gefunden. Bitte den Installationsbefehl von der Projektseite verwenden."
            }
            Write-Failure "rfnegconv konnte nicht geladen werden. Bitte Internetverbindung pr$($script:ue)fen."
        }
        $extra = @('--constraints', $constraints)
    }
    $arguments = @('tool', 'install', '--quiet', '--force', '--python', '3.13') + $extra + @($spec)
    try {
        $result = Invoke-Tool -FilePath $script:Uv -ArgumentList $arguments
    }
    finally {
        if ($constraints) { Remove-Item -LiteralPath $constraints -Force -ErrorAction SilentlyContinue }
    }
    if ($result.ExitCode -ne 0) { Write-Failure 'rfnegconv konnte nicht installiert werden.' }
    Add-ToolBinToPath
    if ($null -eq (Find-App)) { Write-Failure 'rfnegconv wurde installiert, ist aber nicht auffindbar.' }
    # put the tool bin dir on the user PATH for new windows, however uv was installed
    Invoke-Tool -FilePath $script:Uv -ArgumentList @('tool', 'update-shell') -Capture | Out-Null
    Write-Info "$script:Check rfnegconv installiert."
}

function Test-PrivateExifTool {
    if (-not (Test-Path -LiteralPath $script:ExifToolExe)) { return $false }
    try {
        $check = Invoke-Tool -FilePath $script:ExifToolExe -ArgumentList @('-ver') -Capture
        return $check.ExitCode -eq 0
    }
    catch {
        return $false
    }
}

function Install-PrivateExifTool {
    $temp = Join-Path -Path ([IO.Path]::GetTempPath()) -ChildPath ('rfnegconv-exiftool-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $temp | Out-Null
    try {
        $verFile = Join-Path -Path $temp -ChildPath 'ver.txt'
        Get-Download -Uri "$script:ExifToolSite/ver.txt" -OutFile $verFile
        $version = (Get-Content -LiteralPath $verFile -Raw).Trim()
        if ($version -notmatch '^[0-9]+\.[0-9]+$') { return $false }
        $archive = "exiftool-$($version)_64.zip"
        $zip = Join-Path -Path $temp -ChildPath $archive
        try {
            Get-Download -Uri "$script:ExifToolSite/$archive" -OutFile $zip -TimeoutSec 600
        }
        catch {
            Get-Download -Uri "$script:ExifToolMirror/$archive/download" -OutFile $zip -TimeoutSec 600
        }
        $sums = Join-Path -Path $temp -ChildPath 'checksums.txt'
        Get-Download -Uri "$script:ExifToolSite/checksums.txt" -OutFile $sums
        $expected = ''
        foreach ($line in Get-Content -LiteralPath $sums) {
            if ($line.StartsWith("SHA2-256($archive)=")) { $expected = $line.Split('=')[1].Trim() }
        }
        $actual = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash
        if (-not $expected -or $expected -ne $actual) { return $false }
        $unpacked = Join-Path -Path $temp -ChildPath 'unpacked'
        Expand-Archive -LiteralPath $zip -DestinationPath $unpacked -Force
        $folder = Join-Path -Path $unpacked -ChildPath "exiftool-$($version)_64"
        $original = Join-Path -Path $folder -ChildPath 'exiftool(-k).exe'
        if (-not (Test-Path -LiteralPath $original)) { return $false }
        Rename-Item -LiteralPath $original -NewName 'exiftool.exe'
        New-Item -ItemType Directory -Force -Path $script:DataDir | Out-Null
        if (Test-Path -LiteralPath $script:ExifToolDir) {
            Remove-Item -LiteralPath $script:ExifToolDir -Recurse -Force
        }
        Move-Item -LiteralPath $folder -Destination $script:ExifToolDir
        if (-not (Test-PrivateExifTool)) {
            # never leave a broken copy behind; a re-run retries
            Remove-Item -LiteralPath $script:ExifToolDir -Recurse -Force -ErrorAction SilentlyContinue
            return $false
        }
        Write-State -Key 'exiftool' -Value 'private'
        return $true
    }
    catch {
        Write-Verbose "exiftool download failed: $_"
        if ((Test-Path -LiteralPath $script:ExifToolDir) -and -not (Test-PrivateExifTool)) {
            Remove-Item -LiteralPath $script:ExifToolDir -Recurse -Force -ErrorAction SilentlyContinue
        }
        return $false
    }
    finally {
        Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Install-ExifTool {
    $onPath = Get-Command -Name 'exiftool' -CommandType Application -ErrorAction SilentlyContinue
    if ($null -ne $onPath -or (Test-PrivateExifTool)) {
        Write-Info "$script:Check exiftool ist schon da."
        return
    }
    Write-Info "$script:Arrow Installiere exiftool ($($script:ue)bertr$($script:ae)gt Kameradaten in die Fotos; dauert meist h$($script:oe)chstens etwa eine Minute) ..."
    if (Install-PrivateExifTool) {
        Write-Info "$script:Check exiftool installiert."
    }
    else {
        Write-Hint "exiftool konnte nicht installiert werden. Das Programm funktioniert trotzdem, nur ohne Kameradaten in den Fotos."
    }
}

function Initialize-Folder {
    $pictures = $env:RFNEGCONV_PICTURES_DIR
    if (-not $pictures) { $pictures = Get-UserFolder -Folder 'MyPictures' }
    $base = Join-Path -Path $pictures -ChildPath 'rfnegconv'
    Write-Info "$script:Arrow Richte Ordner und Einstellungen ein ..."
    $env:PYTHONIOENCODING = 'utf-8'
    $previousEncoding = $null
    try {
        $previousEncoding = [Console]::OutputEncoding
        [Console]::OutputEncoding = [Text.Encoding]::UTF8
    }
    catch {
        Write-Verbose "console encoding unchanged: $_"  # e.g. no console attached
    }
    try {
        $result = Invoke-Tool -FilePath (Find-App) -Capture -ArgumentList @(
            'config', 'init',
            '--negative', (Join-Path -Path $base -ChildPath 'Negative'),
            '--photos', (Join-Path -Path $base -ChildPath 'Fotos'),
            '--archive', (Join-Path -Path $base -ChildPath 'Archiv'))
    }
    finally {
        if ($null -ne $previousEncoding) {
            try { [Console]::OutputEncoding = $previousEncoding } catch { Write-Verbose "console encoding not restored: $_" }
        }
        Remove-Item -Path Env:PYTHONIOENCODING -ErrorAction SilentlyContinue
    }
    if ($result.ExitCode -ne 0) {
        Write-Hint "Die Einstellungen konnten nicht eingerichtet werden (siehe Meldung oben). Bitte die Datei config.toml pr$($script:ue)fen."
        return $false
    }
    foreach ($line in $result.Output) {
        $parts = "$line".Split([char[]]'=', 2)
        if ($parts.Count -eq 2) { $script:Folders[$parts[0]] = $parts[1] }
    }
    Write-State -Key 'negative_dir' -Value $script:Folders['negative']
    if ($script:Folders['status'] -eq 'kept') {
        Write-Info "$script:Check Vorhandene Einstellungen $($script:ue)bernommen."
    }
    else {
        Write-Info "$script:Check Ordner angelegt."
    }
    return $true
}

function Register-Service {
    if ($script:WithoutService) {
        $script:ServiceRemoved = Unregister-Service
        return $false
    }
    if ($env:RFNEGCONV_NO_SERVICE -eq '1') {
        Write-Info "(Test) Hintergrunddienst $($script:ue)bersprungen - w$($script:ue)rde ausf$($script:ue)hren: rfnegconv service install"
        return $false
    }
    Write-Info "$script:Arrow Starte den Hintergrunddienst ..."
    $result = Invoke-Tool -FilePath (Find-App) -ArgumentList @('service', 'install')
    if ($result.ExitCode -eq 0) {
        Write-Info "$script:Check Hintergrunddienst l$($script:ae)uft."
        return $true
    }
    Write-Hint "Der Hintergrunddienst konnte nicht gestartet werden. Bilder lassen sich trotzdem mit $($script:lq)rfnegconv$($script:rq) umwandeln."
    return $false
}

function Unregister-Service {
    # -OhneDienst: an installed service is removed
    if ($env:RFNEGCONV_NO_SERVICE -eq '1') {
        Write-Info "(Test) Hintergrunddienst $($script:ue)bersprungen - w$($script:ue)rde ausf$($script:ue)hren: rfnegconv service uninstall"
        return $true
    }
    $result = Invoke-Tool -FilePath (Find-App) -ArgumentList @('service', 'uninstall') -Capture
    if ($result.ExitCode -eq 0) {
        Write-Info "$script:Check Kein Hintergrunddienst (umwandeln $($script:ue)ber $($script:lq)$($script:LauncherName)$($script:rq))."
        return $true
    }
    Write-Hint "Der Hintergrunddienst konnte nicht entfernt werden und bleibt eingerichtet. Bitte den Befehl sp$($script:ae)ter noch einmal ausf$($script:ue)hren."
    return $false
}

function Restore-Watcher {
    # The update stopped a running watcher and nothing restarted it (failed
    # install, skipped or failed service step): start it again from autostart.
    if ($env:RFNEGCONV_NO_SERVICE -ne '1') {
        $startup = Join-Path -Path ((Join-Path -Path $env:APPDATA -ChildPath 'Microsoft\Windows\Start Menu\Programs\Startup')) -ChildPath 'rfnegconv.vbs'
        if (Test-Path -LiteralPath $startup) {
            try {
                Start-Process -FilePath 'wscript.exe' -ArgumentList @("`"$startup`"")
                Write-Info "$script:Check Automatische Verarbeitung wieder gestartet."
                return
            }
            catch {
                Write-Verbose "watcher restart failed: $_"
            }
        }
    }
    Write-Hint "Die automatische Verarbeitung wurde f$($script:ue)r das Update beendet und l$($script:ae)uft erst nach der n$($script:ae)chsten Anmeldung wieder. Bis dahin Bilder mit $($script:lq)rfnegconv$($script:rq) umwandeln."
}

function Get-DesktopDir {
    if ($env:RFNEGCONV_DESKTOP_DIR) { return $env:RFNEGCONV_DESKTOP_DIR }
    return [Environment]::GetFolderPath('Desktop')
}

function Add-Shortcut {
    param([string]$Desktop, [string]$Name, [string]$Target, [string]$Key)
    # Only shortcuts this installer created (recorded in the state file) are
    # ever replaced or removed.
    $link = Join-Path -Path $Desktop -ChildPath "$Name.lnk"
    $shell = New-Object -ComObject WScript.Shell
    # ours = recorded by an earlier run and still pointing to the recorded target
    $ours = ((Read-State -Key $Key) -eq $link) -and (Test-Path -LiteralPath $link) -and
        ($shell.CreateShortcut($link).TargetPath -eq (Read-State -Key "$($Key)_target"))
    $blocked = (Test-Path -LiteralPath (Join-Path -Path $Desktop -ChildPath $Name)) -or
        ((Test-Path -LiteralPath $link) -and -not $ours)
    if ($blocked) {
        if ((Read-State -Key $Key) -eq $link) {
            # recorded, but the user changed or replaced it: no longer ours
            Clear-StateKey -Key $Key
            Clear-StateKey -Key "$($Key)_target"
        }
        Write-Hint "Auf dem Schreibtisch gibt es schon $($script:lq)$Name$($script:rq) - nicht ver$($script:ae)ndert."
        return
    }
    $shortcut = $shell.CreateShortcut($link)
    $shortcut.TargetPath = $Target
    $shortcut.Save()
    Write-State -Key $Key -Value $link
    Write-State -Key "$($Key)_target" -Value $Target
    Write-Info "$script:Check Verkn$($script:ue)pfung $($script:lq)$Name$($script:rq) auf dem Schreibtisch."
}

function Add-DesktopShortcut {
    $desktop = Get-DesktopDir
    if (-not $desktop -or -not (Test-Path -LiteralPath $desktop -PathType Container)) { return }
    Add-Shortcut -Desktop $desktop -Name 'Negative' -Target $script:Folders['negative'] -Key 'shortcut_negative'
    Add-Shortcut -Desktop $desktop -Name 'Fotos' -Target $script:Folders['photos'] -Key 'shortcut_photos'
}

# --- launcher "Negative entwickeln": one processing run, then a message box --

$script:LauncherVbs = @'
' "Negative entwickeln" - created by the rfnegconv installer.
' Processes the Negative folder once and shows the result.
Option Explicit
Const Title = "Negative entwickeln"
Dim shell, fso, env, exe, outFile, errFile, q, command, output, entry, summary, detail
Dim processed, failed, photos, text
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
q = Chr(34)
If WScript.Arguments.Count > 0 Then
    ' started by the main run below: a short notice that closes by itself
    If WScript.Arguments(0) = "/notice" Then
        shell.Popup "Negative werden entwickelt " & ChrW(8230), 3, Title, 64
        WScript.Quit 0
    End If
End If
shell.Run "wscript.exe " & q & WScript.ScriptFullName & q & " /notice", 1, False
exe = "__RFNEGCONV__"
outFile = fso.BuildPath(fso.GetSpecialFolder(2), fso.GetTempName())
errFile = fso.BuildPath(fso.GetSpecialFolder(2), fso.GetTempName())
' The paths reach PowerShell as environment variables: no "%" in them is
' ever expanded (neither by shell.Run nor by a command interpreter).
Set env = shell.Environment("Process")
env("RFNEGCONV_LAUNCHER_EXE") = exe
env("RFNEGCONV_LAUNCHER_OUT") = outFile
env("RFNEGCONV_LAUNCHER_ERR") = errFile
command = "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -Command " & q & _
    "Start-Process -FilePath $env:RFNEGCONV_LAUNCHER_EXE -ArgumentList '-Q','run','--summary'" & _
    " -RedirectStandardOutput $env:RFNEGCONV_LAUNCHER_OUT -RedirectStandardError $env:RFNEGCONV_LAUNCHER_ERR" & _
    " -NoNewWindow -Wait" & q
' The summary line is printed last and only when the run took place; without
' it the run failed (the reason is in the "Error:" line), whatever the exit code.
On Error Resume Next
shell.Run command, 0, True
On Error GoTo 0
output = ReadAndDelete(outFile) & vbLf & ReadAndDelete(errFile)

Function ReadAndDelete(path)
    Dim stream
    ReadAndDelete = ""
    If fso.FileExists(path) Then
        If fso.GetFile(path).Size > 0 Then
            Set stream = fso.OpenTextFile(path, 1)
            ReadAndDelete = stream.ReadAll
            stream.Close
        End If
        fso.DeleteFile path, True
    End If
End Function

summary = ""
detail = ""
For Each entry In Split(Replace(output, vbCr, ""), vbLf)
    If Left(entry, 10) = "processed=" Then summary = entry
    If Left(entry, 7) = "Error: " And detail = "" Then detail = Mid(entry, 8)
Next

Function Field(line, name)
    Dim re, found
    Set re = New RegExp
    re.Pattern = name & "=([0-9]+)"
    Set found = re.Execute(line)
    Field = 0
    If found.Count > 0 Then Field = CLng(found(0).SubMatches(0))
End Function

If summary = "" Then
    If detail = "" Then detail = "Das Programm rfnegconv wurde nicht gefunden oder ist abgebrochen."
    text = "Die Negative konnten nicht entwickelt werden." & vbCrLf & vbCrLf & detail
ElseIf Field(summary, "busy") = 1 Then
    text = "Wird gerade im Hintergrund verarbeitet."
Else
    processed = Field(summary, "processed")
    failed = Field(summary, "failed")
    photos = "Fotos"
    If processed = 1 Then photos = "Foto"
    If failed > 0 Then
        text = processed & " " & photos & " fertig, " & failed & " Fehler " & ChrW(8211) & " Details in Negative/_Fehler."
    ElseIf processed > 0 Then
        text = processed & " " & photos & " fertig."
    Else
        text = "Keine neuen Negative gefunden."
    End If
End If
MsgBox text, vbOKOnly + vbInformation + vbSystemModal, Title
'@

function Get-StartMenuDir {
    if ($env:RFNEGCONV_START_MENU_DIR) { return $env:RFNEGCONV_START_MENU_DIR }
    if ($env:APPDATA) { return Join-Path -Path $env:APPDATA -ChildPath 'Microsoft\Windows\Start Menu\Programs' }
    return Get-UserFolder -Folder 'Programs'
}

function Get-LauncherScriptPath {
    return Join-Path -Path $script:DataDir -ChildPath 'negative-entwickeln.vbs'
}

function Test-OurLauncher {
    # recorded by this installer and still starting our script
    param([string]$Link)
    if (-not $Link -or -not $Link.EndsWith('.lnk') -or -not (Test-Path -LiteralPath $Link)) { return $false }
    if ((Read-State -Key 'launcher') -ne $Link) { return $false }
    $arguments = (New-Object -ComObject WScript.Shell).CreateShortcut($Link).Arguments
    return $arguments -eq "`"$(Get-LauncherScriptPath)`""
}

function Add-Launcher {
    # Only a launcher this installer created (state file) is ever replaced.
    $menu = Get-StartMenuDir
    $link = Join-Path -Path $menu -ChildPath "$($script:LauncherName).lnk"
    if ((Test-Path -LiteralPath $link) -and -not (Test-OurLauncher -Link $link)) {
        if ((Read-State -Key 'launcher') -eq $link) { Clear-StateKey -Key 'launcher' }
        Write-Hint "$($script:lq)$($script:LauncherName)$($script:rq) gibt es schon - nicht ver$($script:ae)ndert."
        return
    }
    $vbs = Get-LauncherScriptPath
    New-Item -ItemType Directory -Force -Path $script:DataDir, $menu | Out-Null
    $exe = (Find-App).Replace('"', '""')
    $text = $script:LauncherVbs.Replace("`r`n", "`n").Replace("`n", "`r`n").Replace('__RFNEGCONV__', $exe)
    Set-Content -LiteralPath $vbs -Value $text -Encoding Unicode  # UTF-16 with BOM: any user name
    Write-State -Key 'launcher_script' -Value $vbs
    $wscript = 'wscript.exe'
    if ($env:SystemRoot) { $wscript = Join-Path -Path $env:SystemRoot -ChildPath 'System32\wscript.exe' }
    $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($link)
    $shortcut.TargetPath = $wscript
    $shortcut.Arguments = "`"$vbs`""
    $shortcut.WorkingDirectory = $script:DataDir
    $shortcut.Description = "Negative im Ordner $($script:lq)Negative$($script:rq) jetzt umwandeln"
    $shortcut.Save()
    Write-State -Key 'launcher' -Value $link
    $script:LauncherPlace = "Startmen$($script:ue)"
    Write-Info "$script:Check Programm $($script:lq)$($script:LauncherName)$($script:rq) (im $($script:LauncherPlace))."
}

function Uninstall-Launcher {
    $link = Read-State -Key 'launcher'
    if (Test-OurLauncher -Link $link) { Remove-Item -LiteralPath $link -Force }
    $vbs = Read-State -Key 'launcher_script'
    if ($vbs -and $vbs -eq (Get-LauncherScriptPath)) {
        Remove-Item -LiteralPath $vbs -Force -ErrorAction SilentlyContinue
    }
}

function Show-Summary {
    $app = Find-App
    Write-Info ''
    $versionLine = 'rfnegconv (Version unbekannt)'
    $statusText = ''
    if ($null -ne $app) {
        $version = Invoke-Tool -FilePath $app -ArgumentList @('--version') -Capture
        if ($version.Output.Count -gt 0) { $versionLine = [string]$version.Output[0] }
        $statusText = (Invoke-Tool -FilePath $app -ArgumentList @('service', 'status') -Capture).Output -join "`n"
    }
    $service = 'unbekannt'
    if ($statusText -like '*installed and running*') { $service = "l$($script:ae)uft" }
    elseif ($statusText -like '*installed but not running*') { $service = "eingerichtet, l$($script:ae)uft aber gerade nicht" }
    elseif ($statusText -like '*starts at login*') { $service = 'eingerichtet (startet bei der Anmeldung)' }
    elseif ($statusText -like '*not installed*') { $service = 'nicht eingerichtet' }
    Write-Info "Installiert: $versionLine"
    Write-Info "Hintergrunddienst: $service"
    if ($statusText -like '*exiftool: not found*') { Write-Info 'exiftool: nicht gefunden (Fotos ohne Kameradaten)' }
    elseif ($statusText -like '*exiftool: *') { Write-Info 'exiftool: vorhanden' }
    Write-Info ''
    Write-Info 'Fertig!'
    if ($script:Folders['negative']) {
        Write-Info "  Negative (hier Scans hineinlegen): $($script:Folders['negative'])"
        Write-Info "  Fotos (hier erscheinen die Bilder): $($script:Folders['photos'])"
        Write-Info "  Archiv (fertige Scans):            $($script:Folders['archive'])"
        Write-Info "  Einstellungen:                     $($script:Folders['config'])"
    }
    $launcher = "Programm $($script:lq)$($script:LauncherName)$($script:rq)"
    if ($script:LauncherPlace) { $launcher += " (im $($script:LauncherPlace))" }
    if ($script:WithoutService -and $script:ServiceRemoved) {
        Write-Info "Ohne Hintergrunddienst: Die Umwandlung startet nur $($script:ue)ber das $launcher."
    }
    else {
        Write-Info "Dateien im Ordner $($script:lq)Negative$($script:rq) werden automatisch umgewandelt."
        if ($script:LauncherPlace) { Write-Info "Sofort umwandeln: $launcher." }
    }
    if ($script:WithoutService) {
        Write-Info 'Aktualisieren: powershell -ExecutionPolicy ByPass -c "& ([scriptblock]::Create((irm https://raw.githubusercontent.com/jcmx9/real-fast-negconv/main/install.ps1))) -OhneDienst"'
    }
    else {
        Write-Info "Aktualisieren: denselben Befehl noch einmal ausf$($script:ue)hren."
    }
    Write-Info "Wird $($script:lq)rfnegconv$($script:rq) in PowerShell nicht gefunden: ein neues Fenster $($script:oe)ffnen."
    Write-Info 'Entfernen:     powershell -ExecutionPolicy ByPass -c "& ([scriptblock]::Create((irm https://raw.githubusercontent.com/jcmx9/real-fast-negconv/main/install.ps1))) -Uninstall"'
}

function Install-Everything {
    Write-Info 'rfnegconv - Installation'
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    Install-Uv
    $watcherStopped = $false
    $appInstalled = $false
    try {
        $watcherStopped = Close-RunningApp -Tool $script:AppName -WatcherOnly
        if ($script:ManualRunActive) {
            Write-Failure "Gerade l$($script:ae)uft eine Verarbeitung (zum Beispiel $($script:lq)$($script:LauncherName)$($script:rq)). Sie wird nicht unterbrochen. Bitte warten, bis sie fertig ist, und den Befehl dann noch einmal ausf$($script:ue)hren."
        }
        Install-App
        $appInstalled = $true
    }
    finally {
        # a failed install keeps the old program; its watcher must run again
        if ($watcherStopped -and -not $appInstalled) { Restore-Watcher }
    }
    $serviceStarted = $false
    $serviceRemoved = $false
    if (Initialize-Folder) {
        $serviceStarted = Register-Service
        $serviceRemoved = $script:ServiceRemoved
        Add-DesktopShortcut
        Add-Launcher
    }
    # -OhneDienst: the watcher stopped for the update stays stopped once the
    # service is removed; if removal failed it runs again (Restore-Watcher)
    if ($watcherStopped -and -not $serviceStarted -and -not $serviceRemoved) { Restore-Watcher }
    Install-ExifTool  # optional and online: last, so an abort here loses nothing else
    Show-Summary
}

# --- uninstall --------------------------------------------------------------

function Uninstall-Uv {
    $uvPath = Read-State -Key 'uv'
    if (-not $uvPath) { return }
    Write-Info "$script:Arrow Entferne uv (wurde von diesem Installer eingerichtet) ..."
    if (Test-Path -LiteralPath $uvPath) {
        Invoke-Tool -FilePath $uvPath -ArgumentList @('cache', 'clean') -Capture | Out-Null
        $tools = Invoke-Tool -FilePath $uvPath -ArgumentList @('tool', 'list') -Capture
        # a failed listing proves nothing: then uv's data is kept
        $hasTools = ($tools.ExitCode -ne 0) -or
            (@($tools.Output | Where-Object { "$_" -and -not "$_".StartsWith('No tools') }).Count -gt 0)
        if (-not $hasTools) {
            foreach ($query in @(@('python', 'dir'), @('tool', 'dir'))) {
                $dir = Invoke-Tool -FilePath $uvPath -ArgumentList $query -Capture
                if ($dir.ExitCode -eq 0 -and $dir.Output.Count -gt 0) {
                    Remove-PrivateDir -Path ([string]$dir.Output[0]).Trim()
                }
            }
        }
    }
    $uvDir = Split-Path -Path $uvPath -Parent
    foreach ($name in @('uv.exe', 'uvx.exe', 'uvw.exe')) {
        Remove-Item -LiteralPath (Join-Path -Path $uvDir -ChildPath $name) -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path -LiteralPath (Join-Path -Path $uvDir -ChildPath 'uv.exe')) {
        Write-Hint "uv konnte nicht entfernt werden: $uvDir"
    }
    else {
        Write-Info "$script:Check uv entfernt."
    }
}

function Remove-PrivateDir {
    [CmdletBinding(SupportsShouldProcess = $true)]
    param([string]$Path)
    $roots = @($HOME, (Get-UserFolder -Folder 'LocalApplicationData'), (Get-UserFolder -Folder 'ApplicationData'))
    $inside = $false
    foreach ($root in $roots) {
        if ($root -and $Path.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { $inside = $true }
    }
    if (-not $inside) {
        Write-Hint "Nicht entfernt (liegt nicht im Benutzerordner): $Path"
        return
    }
    if ((Test-Path -LiteralPath $Path) -and $PSCmdlet.ShouldProcess($Path, 'Remove')) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

function Uninstall-Everything {
    Write-Info 'rfnegconv - Entfernen'
    $negative = Read-State -Key 'negative_dir'
    $null = Find-Uv
    if (Find-Uv) {
        Add-ToolBinToPath
        $app = Find-App
        if ($null -ne $app) {
            if ($env:RFNEGCONV_NO_SERVICE -eq '1') {
                Write-Info "(Test) Hintergrunddienst $($script:ue)bersprungen - w$($script:ue)rde ausf$($script:ue)hren: rfnegconv service uninstall"
            }
            else {
                $result = Invoke-Tool -FilePath $app -ArgumentList @('service', 'uninstall')
                if ($result.ExitCode -ne 0) { Write-Hint 'Der Hintergrunddienst konnte nicht entfernt werden.' }
            }
        }
        $null = Close-RunningApp -Tool $script:AppName
        $removed = $true
        if (Test-ToolInstalled -Name $script:AppName) {
            $result = Invoke-Tool -FilePath $script:Uv -ArgumentList @('tool', 'uninstall', $script:AppName) -Capture
            if ($result.ExitCode -ne 0) {
                Write-Hint "$($script:AppName) konnte nicht entfernt werden."
                $removed = $false
            }
        }
        if ($removed) { Write-Info "$script:Check Programm entfernt." }
    }
    else {
        Write-Hint 'uv nicht gefunden - das Programm ist wohl schon entfernt.'
    }
    foreach ($key in @('shortcut_negative', 'shortcut_photos')) {
        $link = Read-State -Key $key
        $target = Read-State -Key "$($key)_target"
        if ($link -and $target -and $link.EndsWith('.lnk') -and (Test-Path -LiteralPath $link)) {
            $current = (New-Object -ComObject WScript.Shell).CreateShortcut($link).TargetPath
            if ($current -eq $target) { Remove-Item -LiteralPath $link -Force }
        }
    }
    Uninstall-Launcher
    if ((Read-State -Key 'exiftool') -eq 'private') {
        Remove-PrivateDir -Path $script:ExifToolDir
        if (Test-Path -LiteralPath $script:ExifToolDir) {
            Write-Hint "exiftool konnte nicht entfernt werden: $script:ExifToolDir"
        }
        else {
            Write-Info "$script:Check exiftool entfernt."
        }
    }
    Uninstall-Uv
    Remove-Item -LiteralPath $script:StateFile -Force -ErrorAction SilentlyContinue
    if ((Test-Path -LiteralPath $script:DataDir) -and -not (Get-ChildItem -LiteralPath $script:DataDir -Force)) {
        Remove-Item -LiteralPath $script:DataDir -Force
    }
    Write-Info ''
    Write-Info "Fertig. Deine Ordner, Bilder und Einstellungen wurden NICHT gel$($script:oe)scht."
    if ($negative) {
        Write-Info "  Sie liegen weiterhin in: $(Split-Path -Path $negative -Parent)"
    }
}

try {
    Initialize-InstallerPath
    if ($Uninstall) {
        Uninstall-Everything
    }
    else {
        Install-Everything
    }
}
finally {
    $ErrorActionPreference = $script:CallerErrorAction
    $ProgressPreference = $script:CallerProgress
}
