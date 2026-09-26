<#
  Construit l'exécutable Windows autonome de la CLI hadi (PyInstaller), à
  partir de cli/main.py — n'a besoin ni de Python ni de pip une fois installé sur
  le poste de l'utilisateur final.

  L'API (voir orchestrator_api/app/api/routes_cli.py, GET /api/cli/download)
  sert ensuite ce binaire tel quel : c'est ce qui permet au tableau de bord
  de proposer un bouton "Télécharger la CLI" sans que personne n'ait à
  taper de commande. Le binaire n'est pas versionné (voir .gitignore) : ce
  script doit avoir tourné au moins une fois sur la machine qui héberge
  l'API pour que ce endpoint ait quelque chose à servir.

  À exécuter depuis la racine du dépôt ou depuis cli/ :
      .\cli\build_exe.ps1
      .\cli\build_exe.ps1 -Clean   # repart de zéro (build/, dist/, spec)

  Ré-exécutable sans risque : écrase simplement le binaire précédent.
#>

param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if ($Clean) {
    Remove-Item -Recurse -Force build, dist, *.spec -ErrorAction SilentlyContinue
}

# PyInstaller n'est qu'un outil de build, jamais une dépendance d'exécution
# de la CLI elle-même — volontairement absent de requirements.txt.
pip install --quiet pyinstaller

pyinstaller --onefile --name hadi-windows --console main.py

Write-Host ""
Write-Host "Exécutable généré : $PSScriptRoot\dist\hadi-windows.exe (livré sous le nom hadi.exe)"
Write-Host "Laisse-le à cet emplacement : c'est là que /api/cli/download va le chercher."
