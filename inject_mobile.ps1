# Injecte le CSS mobile + le design commun dans toutes les pages HTML de l'application.
#  - mobile-responsive.css   : pages normales (gabarits de base + pages autonomes)
#  - design-v2.css / .js     : design commun (toutes les apps sauf tasks-app, qui a son propre design)
#  - mobile-print-pages.css  : pages imprimables (document_pdf*, print.html)
# Idempotent : remplace les blocs existants (marqueurs id="mobile-responsive-v1" et id="design-v2-js").
# Usage : powershell -File inject_mobile.ps1
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$utf8 = New-Object Text.UTF8Encoding($false)
function Lire($f) { [IO.File]::ReadAllText((Join-Path $root $f), [Text.Encoding]::UTF8) }
function Style($css) { "<style id=`"mobile-responsive-v1`">`n" + $css + "</style>`n" }
$blocApp    = Style ((Lire 'mobile-responsive.css') + "`n" + (Lire 'design-v2.css'))
$blocTasks  = Style (Lire 'mobile-responsive.css')
$blocPrint  = Style (Lire 'mobile-print-pages.css')
$blocJs     = "<script id=`"design-v2-js`">`n" + (Lire 'design-v2.js') + "</script>`n"
$viewport  = '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
$skip = '\.bak|-old\.html$'
$patStyle = '(?s)<style id="mobile-responsive-v1">.*?</style>\r?\n?'
$patJs    = '(?s)<script id="design-v2-js">.*?</script>\r?\n?'
$n = 0
Get-ChildItem $root -Recurse -File -Filter *.html | Where-Object { $_.FullName -notmatch $skip } | ForEach-Object {
  $c = [IO.File]::ReadAllText($_.FullName, [Text.Encoding]::UTF8)
  if ($c -notmatch '</head>' -or $c -match '\{%\s*extends') { return }
  $c = [regex]::Replace($c, $patStyle, '')
  $c = [regex]::Replace($c, $patJs, '')
  $imprimable = $_.Name -match 'document_pdf|^print\.html$'
  $taches = $_.FullName -match '\\tasks-app\\'
  if ($imprimable -and $c -notmatch 'name="viewport"') {
    $c = [regex]::Replace($c, '(<meta charset="UTF-8">\r?\n)', "`$1$viewport`n", 1)
  }
  if ($imprimable) { $bloc = $blocPrint } elseif ($taches) { $bloc = $blocTasks } else { $bloc = $blocApp + $blocJs }
  $i = $c.IndexOf('</head>')
  $c = $c.Substring(0, $i) + $bloc + $c.Substring($i)
  [IO.File]::WriteAllText($_.FullName, $c, $utf8)
  Write-Host "OK  $($_.FullName.Substring($root.Length+1))"; $n++
}
Write-Host "$n fichiers mis a jour"
