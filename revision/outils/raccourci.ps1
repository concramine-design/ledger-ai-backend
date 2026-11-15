# Cree le raccourci "Mes revisions" sur le bureau.
# -SiAbsent : ne fait rien si le raccourci existe deja.
param([switch]$SiAbsent)

$app = Split-Path -Parent $PSScriptRoot
$desktop = [Environment]::GetFolderPath('Desktop')
$link = Join-Path $desktop 'Mes revisions.lnk'
if ($SiAbsent -and (Test-Path $link)) { exit 0 }

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($link)
$shortcut.TargetPath = Join-Path $app 'lancer.bat'
$shortcut.WorkingDirectory = $app
$icon = Join-Path $app 'outils\icone.ico'
if (Test-Path $icon) { $shortcut.IconLocation = $icon }
$shortcut.WindowStyle = 7
$shortcut.Description = 'Mes revisions'
$shortcut.Save()
Write-Host "Raccourci cree sur le bureau : $link"
