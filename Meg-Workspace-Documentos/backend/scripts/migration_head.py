"""Use the migration graph as the single authority for application head."""
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def application_head() -> str:
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / 'alembic.ini'))
    config.set_main_option('script_location', str(root / 'alembic'))
    head = ScriptDirectory.from_config(config).get_current_head()
    if head is None:
        raise RuntimeError('Application has no migration head')
    return head
