# Run CamDesk in development mode.
#   .\scripts\run.ps1            -> normal
#   .\scripts\run.ps1 --fake     -> with the built-in fake camera
#   .\scripts\run.ps1 --debug    -> verbose logging
Set-Location (Split-Path $PSScriptRoot -Parent)
uv run python -m camdesk @args
