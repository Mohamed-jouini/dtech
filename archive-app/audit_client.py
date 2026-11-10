"""
audit_client.py — Module partagé pour toutes les apps
Copier dans le répertoire de chaque app Flask.

Usage :
    from audit_client import log_action
    log_action(request, 'fiche-client', 'create', 'client', client_id,
               label='شركة طه فارما', details={'nom': '...'})
"""
import os, json, threading
try:
    import urllib.request as _urllib
except ImportError:
    _urllib = None

# URL lue à chaque appel pour capturer les env vars tardives
def _get_audit_url():
    return os.environ.get('AUDIT_URL', 'http://audit-app:5010/api/log')
NEXTCLOUD_URL = os.environ.get('NEXTCLOUD_URL', 'http://cabinet.mwj-lawyers.com')

# Cache utilisateurs Nextcloud : {cookie_hash: (username, display, timestamp)}
_user_cache = {}
_CACHE_TTL  = 300  # 5 minutes


def _get_nc_user_from_cookies(cookies_str):
    """Identifier l'utilisateur Nextcloud depuis la chaîne de cookies."""
    import time, hashlib
    if not cookies_str:
        return 'inconnu', ''

    cache_key = hashlib.md5(cookies_str.encode()).hexdigest()
    now = time.time()

    if cache_key in _user_cache:
        username, display, ts = _user_cache[cache_key]
        if now - ts < _CACHE_TTL:
            return username, display

    try:
        nc_api = f"{NEXTCLOUD_URL}/ocs/v2.php/cloud/user?format=json"
        req = _urllib.Request(nc_api, headers={
            'Cookie': cookies_str,
            'OCS-APIRequest': 'true',
            'Accept': 'application/json',
        })
        with _urllib.urlopen(req, timeout=3) as r:
            data = json.loads(r.read().decode())
        user_data = data.get('ocs', {}).get('data', {})
        username  = user_data.get('id', 'inconnu')
        display   = user_data.get('display-name', '') or user_data.get('displayname', '')
        _user_cache[cache_key] = (username, display, now)
        return username, display
    except Exception:
        return 'inconnu', ''


def _get_nc_user(request):
    cookies_str = '; '.join(f'{k}={v}' for k, v in request.cookies.items())
    return _get_nc_user_from_cookies(cookies_str)


def log_action(request, app_name, action, entity_type, entity_id='',
               label='', details=None):
    AUDIT_URL = _get_audit_url()
    if not AUDIT_URL:
        return

    # Extraire TOUTES les données du request AVANT le thread
    # (le contexte Flask est détruit après la réponse)
    try:
        cookies_str = '; '.join(f'{k}={v}' for k, v in request.cookies.items())
        ip = (request.headers.get('X-Real-IP') or
              request.headers.get('X-Forwarded-For', '').split(',')[0].strip() or
              getattr(request, 'remote_addr', '') or '')
    except Exception:
        cookies_str = ''
        ip = ''

    def _send():
        try:
            # Identifier l'utilisateur NC avec les cookies extraits
            nc_user, nc_display = _get_nc_user_from_cookies(cookies_str)
            payload = json.dumps({
                'app':          app_name,
                'action':       action,
                'entity_type':  entity_type,
                'entity_id':    str(entity_id),
                'entity_label': label,
                'nc_user':      nc_user,
                'nc_display':   nc_display,
                'details':      details or {},
                'ip':           ip,
            }, ensure_ascii=False).encode('utf-8')
            req = _urllib.Request(
                AUDIT_URL, data=payload,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            _urllib.urlopen(req, timeout=2)
        except Exception:
            pass

    t = threading.Thread(target=_send, daemon=True)
    t.start()
