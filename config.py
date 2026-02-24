from calibre.utils.config import JSONConfig

prefs = JSONConfig('plugins/opds_client')

prefs.defaults['servers'] = []
prefs.defaults['last_server'] = 0


def load_servers():
    servers = prefs.get('servers', [])
    # 하위 호환: auth 필드 없는 레거시 항목은 "basic"으로 처리
    for s in servers:
        if 'auth' not in s:
            s['auth'] = 'basic'
    return servers


def save_servers(servers):
    prefs['servers'] = servers


def get_last_server():
    return prefs.get('last_server', 0)


def set_last_server(index):
    prefs['last_server'] = index
