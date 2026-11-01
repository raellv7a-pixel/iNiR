#!/usr/bin/env python3
"""Prepare executáveis locais do Skwd em cache, sem instalar nem ativar serviços."""
import json
import os
from pathlib import Path
import tempfile

PROJECTS = Path(__file__).resolve().parents[2]
REQUIRED = {
    'skwd-wall-v2': PROJECTS / 'skwd-wall/target/debug/skwd-wall',
    'skwd-walld': PROJECTS / 'skwd-deck/target/debug/skwd-walld',
    'skwd-wall-scan': PROJECTS / 'skwd-deck/target/debug/skwd-wall-scan',
    'skwd-wall-effects': PROJECTS / 'skwd-deck/target/debug/skwd-wall-effects',
    'skwd-helm': PROJECTS / 'skwd-deck/target/debug/skwd-helm',
    'skwd-paper-v2': PROJECTS / 'skwd-paper/target/debug/skwd-paper',
    'skwd-wall-still': PROJECTS / 'skwd-paper/target/debug/skwd-wall-still',
    'skwd-wall-vk': PROJECTS / 'skwd-paper/target/debug/skwd-wall-vk',
}
OPTIONAL = {
    'skwd-steam': PROJECTS / 'skwd-deck/target/debug/skwd-steam',
    'skwd-lens': PROJECTS / 'skwd-lens/target/debug/skwd-lens',
    'skwd-paper-tinier': PROJECTS / 'skwd-paper/target/debug/skwd-paper-tinier',
}


def main():
    missing = [str(path) for path in REQUIRED.values() if not path.is_file() or not os.access(path, os.X_OK)]
    if missing:
        print('Compile os executáveis ausentes antes de preparar o ambiente:')
        for path in missing:
            print('  ' + path)
        return 1
    cache = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache')))
    cache.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix='inir-skwd-staging-', dir=cache))
    bindir = directory / 'bin'
    bindir.mkdir(mode=0o700)
    installed = {}
    for name, path in (REQUIRED | OPTIONAL).items():
        if not path.is_file() or not os.access(path, os.X_OK):
            continue
        (bindir / name).symlink_to(path.resolve())
        installed[name] = str(path.resolve())
    (directory / 'manifest.json').write_text(json.dumps(installed, ensure_ascii=False, indent=2) + '\n')
    print(f'Executáveis preparados em: {bindir}')
    absent = [name for name in OPTIONAL if name not in installed]
    if absent:
        print('Auxiliares opcionais indisponíveis: ' + ', '.join(absent))
    print('Nenhum serviço ou arquivo da instalação ativa foi alterado.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
