<#
.SYNOPSIS
    Flujo oficial para actualizar el catálogo de Sugoi Posters con Cloudflare R2 y Firebase Hosting.

.DESCRIPTION
    1. Normaliza espacios, '#' y caracteres no-ASCII en C-a, S-u, P-o, S-e, Pol (Quitar_espacios.py).
    2. Regenera products.dart con URLs de https://img.sugoipostershn.com/ y lo sincroniza a SugoiPosters-Web-App (productos.py).
    3. Con -Push: hace commit y push en Sugoi-Posters-Assets y espera a que GitHub Actions
       sincronice originales + miniaturas (360px/640px) al bucket R2 `sugoi-posters-assets`.
    4. Con -Deploy: además compila y despliega SugoiPosters-Web-App con `build_web.ps1 -Deploy`
       una vez confirmado que R2 terminó en verde (cero imágenes rotas).

.EXAMPLE
    .\publicar_catalogo.ps1
    # Solo normaliza nombres y regenera products.dart (sin push ni deploy).

.EXAMPLE
    .\publicar_catalogo.ps1 -Push -Message "feat(catalogo): nuevas camisas Dandadan"
    # Normaliza, regenera products.dart, hace push y espera la sincronización de R2.

.EXAMPLE
    .\publicar_catalogo.ps1 -Deploy -Message "feat(catalogo): nuevas camisas Dandadan"
    # Flujo completo: normaliza -> products.dart -> push -> espera R2 -> compila y despliega Web App.
#>

param(
    [switch]$Push,
    [switch]$Deploy,
    [switch]$PushWebApp,
    [string]$Message = "chore(catalogo): actualizar imagenes y catalogo"
)

$ErrorActionPreference = 'Stop'

$AssetsDir = $PSScriptRoot
$WebAppDir = Join-Path (Split-Path $AssetsDir -Parent) "SugoiPosters-Web-App"
$RepoSlug  = "Milo-IZ/Sugoi-Posters-Assets"
$Workflow  = "Sync Assets to Cloudflare R2"

if ($Deploy) {
    $Push = $true
}

Set-Location $AssetsDir

Write-Host "==> 1/4 Normalizando nombres de archivos y carpetas (ASCII seguro)..." -ForegroundColor Cyan
python Quitar_espacios.py
if ($LASTEXITCODE -ne 0) { throw "Falló Quitar_espacios.py" }

Write-Host "==> 2/4 Regenerando products.dart (https://img.sugoipostershn.com/)..." -ForegroundColor Cyan
python productos.py
if ($LASTEXITCODE -ne 0) { throw "Falló productos.py" }

Write-Host "==> Estado actual en Sugoi-Posters-Assets:" -ForegroundColor Cyan
$status = git status -s
if ($status) {
    $status | ForEach-Object { Write-Host "   $_" }
} else {
    Write-Host "   (sin cambios pendientes)" -ForegroundColor DarkGray
}

if (-not $Push) {
    Write-Host ""
    Write-Host "Listo localmente. Para subir a R2 y desplegar la web ejecuta:" -ForegroundColor Green
    Write-Host "  .\publicar_catalogo.ps1 -Deploy -Message `"feat(catalogo): descripcion`"" -ForegroundColor Yellow
    exit 0
}

Write-Host "==> 3/4 Subiendo cambios a GitHub para sincronizar Cloudflare R2..." -ForegroundColor Cyan
$pushedCommit = $false
if ($status) {
    git add -A
    if ($LASTEXITCODE -ne 0) { throw "Falló git add" }

    git commit -m $Message
    if ($LASTEXITCODE -ne 0) { throw "Falló git commit" }

    git push origin main
    if ($LASTEXITCODE -ne 0) { throw "Falló git push origin main" }
    $pushedCommit = $true
} else {
    Write-Host "   Sin cambios nuevos en Sugoi-Posters-Assets para subir." -ForegroundColor DarkGray
}

if ($pushedCommit) {
    $headSha = (git rev-parse HEAD).Trim()
    $changedFiles = git -c core.quotepath=false diff-tree --no-commit-id --name-only -r $headSha
    $touchedImages = $changedFiles | Where-Object { $_ -match '^(C-a|S-u|P-o|S-e|Pol)/' }

    if ($touchedImages) {
        $ghCmd = Get-Command gh -ErrorAction SilentlyContinue
        if ($ghCmd) {
            Write-Host "   Esperando a que GitHub Actions sincronice Cloudflare R2 (commit $($headSha.Substring(0,7)))..." -ForegroundColor Cyan
            $runId = $null
            for ($i = 0; $i -lt 10; $i++) {
                Start-Sleep -Seconds 3
                $candidate = gh run list -R $RepoSlug --workflow $Workflow --commit $headSha --json databaseId --jq ".[0].databaseId" 2>$null
                if ($candidate -and $candidate.Trim() -match '^\d+$') {
                    $runId = $candidate.Trim()
                    break
                }
            }
            if ($runId) {
                gh run watch $runId -R $RepoSlug --exit-status
                if ($LASTEXITCODE -ne 0) {
                    throw "La sincronización a Cloudflare R2 falló (run $runId). Se cancela el deploy para evitar imágenes rotas."
                }
                Write-Host "   [OK] Cloudflare R2 sincronizado correctamente." -ForegroundColor Green
            } else {
                Write-Warning "No se detectó el run de GitHub Actions en 30s. Revisa https://github.com/$RepoSlug/actions antes de desplegar."
                if ($Deploy) {
                    throw "Deploy cancelado por seguridad hasta confirmar la sincronización en R2."
                }
            }
        } else {
            Write-Warning "GitHub CLI ('gh') no está instalado; verifica manualmente en https://github.com/$RepoSlug/actions que el sync de R2 haya terminado en verde."
        }
    } else {
        Write-Host "   El commit no modificó imágenes del catálogo; no se requiere sync de R2." -ForegroundColor DarkGray
    }
}

if (-not $Deploy) {
    Write-Host "==> Listo (R2 sincronizado)." -ForegroundColor Green
    exit 0
}

if (-not (Test-Path (Join-Path $WebAppDir "tools\build_web.ps1"))) {
    throw "No se encontró SugoiPosters-Web-App en: $WebAppDir"
}

Write-Host "==> 4/4 Compilando y desplegando SugoiPosters-Web-App a Firebase Hosting..." -ForegroundColor Cyan
Set-Location $WebAppDir
& ".\tools\build_web.ps1" -Deploy
if ($LASTEXITCODE -ne 0) { throw "Falló build_web.ps1 -Deploy" }

if ($PushWebApp) {
    $webStatus = git status -s -- lib/data/products.dart
    if ($webStatus) {
        git add lib/data/products.dart
        git commit -m $Message
        git push origin main
    }
}

Write-Host "==> Catálogo publicado en Cloudflare R2 y Firebase Hosting con éxito." -ForegroundColor Green
