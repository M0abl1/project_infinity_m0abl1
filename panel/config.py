import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    root: Path
    state: Path
    owner: str
    bind: str
    port: int = 8787
    process: str = 'project-infinity'
    demo: bool = False
    backup_keep: int = 0

    @classmethod
    def load(cls):
        demo = os.getenv('PANEL_DEMO') == '1'
        return cls(
            Path(os.getenv('MINE_ROOT', '/home/mine/mine_servers/project-infinity')).resolve(),
            Path(os.getenv('PANEL_STATE', str(Path.home() / '.local/share/minecraft-panel'))).resolve(),
            os.getenv('PANEL_OWNER', '').lower(),
            os.getenv('PANEL_BIND', '127.0.0.1'),
            int(os.getenv('PANEL_PORT', '8787')),
            os.getenv('MINE_PM2_NAME', 'project-infinity'), demo,
            int(os.getenv('PANEL_BACKUP_KEEP', '0')),
        )
