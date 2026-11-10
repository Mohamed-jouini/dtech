"""Conversion de montants en lettres (français, TND/millimes)"""

UNITS = ['', 'un', 'deux', 'trois', 'quatre', 'cinq', 'six', 'sept', 'huit', 'neuf',
         'dix', 'onze', 'douze', 'treize', 'quatorze', 'quinze', 'seize',
         'dix-sept', 'dix-huit', 'dix-neuf']
TENS  = ['', '', 'vingt', 'trente', 'quarante', 'cinquante', 'soixante',
         'soixante', 'quatre-vingt', 'quatre-vingt']

def _below_1000(n):
    if n == 0:   return ''
    if n  < 20:  return UNITS[n]
    if n  < 100:
        t, u = divmod(n, 10)
        if t == 7:
            return TENS[t] + ('-' if u else '') + (UNITS[10+u] if u else 'dix')
        if t == 9:
            return TENS[t] + ('-' if u else 's' if u==0 else '') + (UNITS[10+u] if u else 'dix')
        if u == 1 and t not in (8, 9):
            return TENS[t] + '-et-un'
        return TENS[t] + ('-' if u else ('s' if t==8 else '')) + (UNITS[u] if u else '')
    c, r = divmod(n, 100)
    if c == 1:
        return 'cent' + (' ' + _below_1000(r) if r else '')
    return UNITS[c] + ' cent' + ('' if r else 's') + (' ' + _below_1000(r) if r else '')

def _int_to_fr(n):
    if n == 0: return 'zéro'
    if n < 0:  return 'moins ' + _int_to_fr(-n)
    parts = []
    if n >= 1_000_000:
        m, n = divmod(n, 1_000_000)
        parts.append(_below_1000(m) + ' million' + ('s' if m > 1 else ''))
    if n >= 1000:
        k, n = divmod(n, 1000)
        parts.append(('mille' if k == 1 else _below_1000(k) + ' mille'))
    if n: parts.append(_below_1000(n))
    return ' '.join(p for p in parts if p).strip()

def montant_en_lettres(montant):
    """Convertit un montant TND en lettres. Ex: 1234.560 → 'Mille deux cent trente-quatre dinars et cinq cent soixante millimes'"""
    try:
        montant = round(float(montant), 3)
        dinars   = int(montant)
        millimes = round((montant - dinars) * 1000)
        d_str = _int_to_fr(dinars).capitalize()
        result = d_str + (' dinar' if dinars <= 1 else ' dinars')
        if millimes > 0:
            m_str = _int_to_fr(millimes)
            result += ' et ' + m_str + (' millime' if millimes <= 1 else ' millimes')
        return result
    except Exception:
        return ''
