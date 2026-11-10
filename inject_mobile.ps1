# Injecte le CSS mobile dans toutes les pages HTML de l'application.
#  - mobile-responsive.css   : pages normales (gabarits de base + pages autonomes)
#  - mobile-print-pages.css  : pages imprimables (document_pdf*, print.html)
# Idempotent : remplace le bloc existant (marqueur id="mobile-responsive-v1").
# Usage : powershell -File inject_mobile.ps1
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$utf8 = New-Object Text.UTF8Encoding($false)
function Bloc($f) { "<style id=`"mobile-responsive-v1`">`n" + [IO.File]::ReadAllText((Join-Path $root $f), [Text.Encoding]::UTF8) + "</style>`n" }
$blocApp   = Bloc 'mobile-responsive.css'
$blocPrint = Bloc 'mobile-print-pages.css'
$viewport  = '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
$skip = '\.bak|-old\.html$'
$pattern = '(?s)<style id="mobile-responsive-v1">.*?</style>\r?\n?'
$n = 0
Get-ChildItem $root -Recurse -File -Filter *.html | Where-Object { $_.FullName -notmatch $skip } | ForEach-Object {
  $c = [IO.File]::ReadAllText($_.FullName, [Text.Encoding]::UTF8)
  if ($c -notmatch '</head>' -or $c -match '\{%\s*extends') { return }
  $c = [regex]::Replace($c, $pattern, '')
  $imprimable = $_.Name -match 'document_pdf|^print\.html$'
  if ($imprimable -and $c -notmatch 'name="viewport"') {
    $c = [regex]::Replace($c, '(<meta charset="UTF-8">\r?\n)', "`$1$viewport`n", 1)
  }
  $i = $c.IndexOf('</head>')
  $c = $c.Substring(0, $i) + $(if ($imprimable) { $blocPrint } else { $blocApp }) + $c.Substring($i)
  [IO.File]::WriteAllText($_.FullName, $c, $utf8)
  Write-Host "OK  $($_.FullName.Substring($root.Length+1))"; $n++
}
Write-Host "$n fichiers mis a jour"
