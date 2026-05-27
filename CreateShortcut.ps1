param(
    [string]$AppDir = (Split-Path -Parent $MyInvocation.MyCommand.Path)
)

$desktop = [Environment]::GetFolderPath('Desktop')
$exePath = Join-Path $AppDir 'VideoGenerator.exe'
$vbsPath = Join-Path $AppDir 'start.vbs'
$icoPath = Join-Path $AppDir 'icon.ico'
$icoPath2 = Join-Path $AppDir 'assets\icon.ico'
$lnkPath = Join-Path $desktop 'VideoGenerator.lnk'

$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut($lnkPath)

if (Test-Path $exePath) {
    $sc.TargetPath = $exePath
    $sc.IconLocation = "$exePath,0"
} elseif (Test-Path $vbsPath) {
    $sc.TargetPath = $vbsPath
    if (Test-Path $icoPath) {
        $sc.IconLocation = "$icoPath,0"
    } elseif (Test-Path $icoPath2) {
        $sc.IconLocation = "$icoPath2,0"
    }
} else {
    Write-Host '  [ERROR] exe or vbs not found'
    exit 1
}

$sc.Save()
Write-Host '  [OK] Shortcut created'
