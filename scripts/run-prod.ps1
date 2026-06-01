# Lance l'application avec les paramètres production (test NetHSM réel).
# Usage : copier .env.example vers .env, renseigner les valeurs, puis :
#   .\scripts\run-prod.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$EnvFile = Join-Path $Root ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') { return }
        $name = $Matches[1]
        $value = $Matches[2].Trim().Trim('"').Trim("'")
        Set-Item -Path "Env:$name" -Value $value
    }
}

if (-not $env:DJANGO_SETTINGS_MODULE) { $env:DJANGO_SETTINGS_MODULE = "config.settings_prod" }
if (-not $env:DJANGO_DEBUG) { $env:DJANGO_DEBUG = "false" }

.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py collectstatic --noinput
Write-Host "Serveur prod (settings_prod) sur http://127.0.0.1:8000"
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
