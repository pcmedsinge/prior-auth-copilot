# fetch_igs.ps1 — download IG package tarballs into docker/hapi/igs/
# Run once before `make fhir-up` (or `docker compose up`) on a fresh checkout.
# Requires: PowerShell 5.1+ or PowerShell 7+

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$IgsDir = Join-Path $ScriptDir "igs"
New-Item -ItemType Directory -Force -Path $IgsDir | Out-Null

$Packages = @(
    @{
        File = "hl7.fhir.us.core-6.1.0.tgz"
        Url  = "https://packages.fhir.org/hl7.fhir.us.core/6.1.0"
    },
    @{
        File = "hl7.fhir.us.davinci-pas-2.0.1.tgz"
        Url  = "https://packages.fhir.org/hl7.fhir.us.davinci-pas/2.0.1"
    }
)

foreach ($pkg in $Packages) {
    $Dest = Join-Path $IgsDir $pkg.File
    if (Test-Path $Dest) {
        Write-Host "[skip] $($pkg.File) already present"
        continue
    }
    Write-Host "[fetch] $($pkg.File) ..."
    Invoke-WebRequest -Uri $pkg.Url -OutFile $Dest -UseBasicParsing
    Write-Host "[ok]   $($pkg.File)"
}

Write-Host "All IGs present in $IgsDir"
