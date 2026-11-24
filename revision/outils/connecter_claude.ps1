# Enregistre le serveur MCP "revision" dans l'application Claude pour ordinateur
# et active la preparation des lecons par Claude dans le fichier .env.
$ErrorActionPreference = 'Stop'
$app = Split-Path -Parent $PSScriptRoot
$python = Join-Path $app '.venv\Scripts\python.exe'
$launcher = Join-Path $app 'backend\mcp_revision.py'

if (-not (Test-Path $python)) {
    Write-Host "Lance d'abord installer.bat, puis relance connecter_claude.bat."
    exit 1
}

# Dossiers de configuration de l'application Claude (installation classique et version Microsoft Store).
$targets = @(Join-Path $env:APPDATA 'Claude')
$packages = Join-Path $env:LOCALAPPDATA 'Packages'
if (Test-Path $packages) {
    foreach ($pkg in Get-ChildItem $packages -Directory -Filter 'Claude_*' -ErrorAction SilentlyContinue) {
        $targets += (Join-Path $pkg.FullName 'LocalCache\Roaming\Claude')
    }
}

$entry = [ordered]@{ command = $python; args = @($launcher) }
foreach ($dir in $targets) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $file = Join-Path $dir 'claude_desktop_config.json'
    $config = $null
    if (Test-Path $file) {
        Copy-Item $file "$file.sauvegarde" -Force
        $raw = [IO.File]::ReadAllText($file)
        if ($raw.Trim()) {
            try { $config = $raw | ConvertFrom-Json }
            catch {
                Write-Host "Le fichier $file est illisible : il n'a pas ete modifie."
                continue
            }
        }
    }
    if ($null -eq $config) { $config = New-Object PSObject }
    if (-not ($config.PSObject.Properties.Name -contains 'mcpServers')) {
        $config | Add-Member -NotePropertyName mcpServers -NotePropertyValue (New-Object PSObject)
    }
    $config.mcpServers | Add-Member -NotePropertyName revision -NotePropertyValue $entry -Force
    $json = $config | ConvertTo-Json -Depth 20
    [IO.File]::WriteAllText($file, $json, (New-Object Text.UTF8Encoding $false))
    Write-Host "Claude configure : $file"
}

# Active la preparation par Claude dans .env (cree a partir de .env.example si besoin).
$envFile = Join-Path $app '.env'
if (-not (Test-Path $envFile)) { Copy-Item (Join-Path $app '.env.example') $envFile }
$lines = [IO.File]::ReadAllLines($envFile)
$found = $false
for ($i = 0; $i -lt $lines.Length; $i++) {
    if ($lines[$i] -match '^\s*PREPARATION_PAR\s*=') { $lines[$i] = 'PREPARATION_PAR=claude'; $found = $true }
}
if (-not $found) { $lines += 'PREPARATION_PAR=claude' }
[IO.File]::WriteAllLines($envFile, $lines, (New-Object Text.UTF8Encoding $false))

Write-Host ""
Write-Host "C'est fait. Il reste deux choses :"
Write-Host " 1. Ferme completement l'application Claude (icone pres de l'horloge : Quitter), puis rouvre-la."
Write-Host " 2. Ferme la fenetre noire de Mes revisions et relance le raccourci du bureau."
Write-Host "Ensuite, chaque soir ou chaque matin, ecris dans Claude : Prepare les lecons."
