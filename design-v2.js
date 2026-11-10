/* ===== DESIGN v2 (script) =====
   Prépare les tableaux pour l'affichage en fiches sur téléphone :
   - étiquette de chaque cellule (data-label) = titre de sa colonne ;
   - cellule « # », première colonne utile, colonne d'actions, cellules vides ;
   - lignes de regroupement (une seule cellule sur toute la largeur).
   Suit aussi les tableaux construits en JavaScript après chargement (MutationObserver).
   Tableaux exclus : .no-cards, .mt-table, .ctx-table, ceux qui contiennent des champs de saisie. */
(function () {
  var EXCLUS = '.no-cards, .mt-table, .ctx-table';
  function txt(el) { return (el.textContent || '').replace(/\s+/g, ' ').trim(); }
  function vide(td) {
    if (td.querySelector('img, select, input, button, a, svg, form')) return false;
    return txt(td).replace(/[—–\-]/g, '') === '';
  }
  /* Titres par colonne, en tenant compte des en-têtes sur deux lignes (colspan / rowspan) :
     « groupe — sous-titre » quand une colonne appartient à un groupe. */
  function titres(table) {
    var rows = table.tHead ? table.tHead.rows : null;
    if (!rows || !rows.length) return null;
    var grille = [];
    for (var r = 0; r < rows.length; r++) {
      grille[r] = grille[r] || [];
      var c = 0;
      Array.prototype.forEach.call(rows[r].cells, function (th) {
        while (grille[r][c] !== undefined) c++;
        var cs = parseInt(th.getAttribute('colspan') || '1', 10) || 1;
        var rs = parseInt(th.getAttribute('rowspan') || '1', 10) || 1;
        for (var i = 0; i < rs; i++) for (var j = 0; j < cs; j++) {
          grille[r + i] = grille[r + i] || [];
          grille[r + i][c + j] = { t: txt(th), multi: cs > 1 };
        }
        c += cs;
      });
    }
    var der = grille[grille.length - 1] || [], out = [];
    for (var k = 0; k < der.length; k++) {
      var bas = der[k] ? der[k].t : '', haut = grille[0][k];
      out.push(haut && haut.multi && haut.t && haut.t !== bas ? haut.t + ' — ' + bas : bas);
    }
    return out;
  }
  function preparer(table) {
    if (table.matches(EXCLUS) || table.closest('.no-cards')) return;
    var tb = table.tBodies && table.tBodies[0];
    if (!tb) return;
    if (tb.querySelector('input:not([type=hidden]):not([type=checkbox]), textarea')) return;  // tableau de saisie : on laisse le défilement
    var h = titres(table);
    if (!h || !h.length) return;
    table.classList.add('tbl-cards');
    var numFirst = /^(#|ع\.?|n°|no)$/i.test(h[0] || '');
    var premier = numFirst ? 1 : 0;
    Array.prototype.forEach.call(tb.rows, function (tr) {
      var cells = tr.cells;
      if (cells.length === 1 && (parseInt(cells[0].getAttribute('colspan') || '1', 10) > 1 || h.length > 1)) {
        tr.classList.add('tr-group'); return;
      }
      var col = 0;
      Array.prototype.forEach.call(cells, function (td) {
        var lab = h[col] || '';
        col += parseInt(td.getAttribute('colspan') || '1', 10) || 1;
        if (lab && td.getAttribute('data-label') !== lab) td.setAttribute('data-label', lab);
        var actions = /إجراءات|actions|تفاصيل$/i.test(lab) ||
                      (td.querySelector('a, button') && !txt(td).replace(/[^؀-ۿa-zA-Z0-9]/g, '').length);
        td.classList.toggle('td-actions', !!actions);
        td.classList.toggle('td-num', numFirst && td === cells[0]);
        td.classList.toggle('td-first', td === cells[premier] && !actions);
        td.classList.toggle('td-empty', !actions && td !== cells[premier] && vide(td));
        var long = !actions && txt(td).length > 38;
        td.classList.toggle('td-wide', long);
      });
    });
  }
  /* Pastilles de statut et dates dans les cellules texte simples */
  var STATUTS = {
    'منجز': '#2E9E57', 'منجزة': '#2E9E57', 'محكوم فيها': '#2E9E57', 'مدفوعة': '#2E9E57', 'Payé': '#2E9E57', 'Payée': '#2E9E57',
    'في الانتظار': '#B5862B', 'قيد الانتظار': '#B5862B', 'تصريح': '#B5862B', 'تصريح بالحكم': '#B5862B', 'En cours': '#B5862B', 'Brouillon': '#8C867E',
    'جارية': '#2C65AE', 'جاري': '#2C65AE', 'Validé': '#2C65AE', 'ملغى': '#C25B4A', 'Annulé': '#C25B4A', 'متأخر': '#C25B4A', 'متأخرة': '#C25B4A'
  };
  var auj = new Date(); auj = auj.getFullYear() + '-' + ('0' + (auj.getMonth() + 1)).slice(-2) + '-' + ('0' + auj.getDate()).slice(-2);
  function decorer(table) {
    if (table.matches(EXCLUS)) return;
    var tb = table.tBodies && table.tBodies[0]; if (!tb) return;
    Array.prototype.forEach.call(tb.querySelectorAll('td'), function (td) {
      if (td.children.length || td.dataset.deco) return;
      var t = txt(td);
      if (STATUTS[t]) {
        td.dataset.deco = '1';
        td.innerHTML = '<span class="d-pill" style="--c:' + STATUTS[t] + '">' + td.innerHTML.trim() + '</span>';
      } else if (/^\d{4}-\d{2}-\d{2}$/.test(t)) {
        td.dataset.deco = '1';
        td.innerHTML = '<span class="d-date' + (t === auj ? ' is-today' : '') + '">' + t + '</span>';
      }
    });
  }
  /* Titre de page : la première icône (emoji) devient une pastille */
  function titrePage() {
    Array.prototype.forEach.call(document.querySelectorAll('.header h1, .app-header h1'), function (h1) {
      if (h1.querySelector('.h-ico')) return;
      var n = h1.firstChild;
      while (n && n.nodeType === 3 && !n.nodeValue.trim()) n = n.nextSibling;
      if (!n || n.nodeType !== 3) return;
      var m = n.nodeValue.match(/^\s*((?:\p{Extended_Pictographic}|\p{Regional_Indicator})(?:️|‍\p{Extended_Pictographic})*)\s*/u);
      if (!m) return;
      var ico = document.createElement('span'); ico.className = 'h-ico'; ico.textContent = m[1];
      n.nodeValue = n.nodeValue.slice(m[0].length);
      h1.insertBefore(ico, n);
    });
  }
  function tout() {
    Array.prototype.forEach.call(document.querySelectorAll('table'), function (t) { preparer(t); decorer(t); });
    titrePage();
  }
  var attente = null;
  function plusTard() { if (attente) return; attente = setTimeout(function () { attente = null; tout(); }, 60); }
  function demarrer() {
    tout();
    if (window.MutationObserver) {
      new MutationObserver(function (muts) {
        for (var i = 0; i < muts.length; i++) {
          var t = muts[i].target;
          if (t && t.closest && (t.closest('table') || t.querySelector && t.querySelector('table'))) { plusTard(); return; }
        }
      }).observe(document.body, { childList: true, subtree: true });
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', demarrer); else demarrer();
})();
