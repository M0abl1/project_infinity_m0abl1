import ipaddress
import uvicorn
from panel.config import Settings
from panel.main import create_app

if __name__ == '__main__':
    settings = Settings.load()
    ip = ipaddress.ip_address(settings.bind)
    if settings.demo:
        if not ip.is_loopback:
            raise SystemExit('Demonstração permitida apenas em loopback.')
    elif not settings.owner or ip not in ipaddress.ip_network('100.64.0.0/10'):
        raise SystemExit('Configure PANEL_OWNER e PANEL_BIND com o IPv4 do Tailscale.')
    uvicorn.run(create_app(settings), host=settings.bind, port=settings.port,
                proxy_headers=False, workers=1, limit_concurrency=24,
                timeout_keep_alive=5)
