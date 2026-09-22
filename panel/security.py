import ipaddress
import json
import subprocess


def tailscale_identity(address, owner):
    """Resolve the TCP peer, never a browser-supplied proxy/identity header."""
    ip = ipaddress.ip_address(address)
    if not owner or not (ip in ipaddress.ip_network('100.64.0.0/10') or ip in ipaddress.ip_network('fd7a:115c:a1e0::/48')):
        raise PermissionError('Acesso permitido apenas ao proprietário pelo Tailscale.')
    try:
        result = subprocess.run(['tailscale', 'whois', '--json', str(ip)],
                                capture_output=True, text=True, check=True, timeout=5)
        data = json.loads(result.stdout)
        login = data.get('UserProfile', {}).get('LoginName', '').lower()
        if data.get('Node', {}).get('Tags') or login != owner:
            raise PermissionError('Identidade sem permissão para acessar este painel.')
        return login
    except (subprocess.SubprocessError, ValueError, OSError) as exc:
        raise PermissionError('Não foi possível validar a identidade no Tailscale.') from exc
