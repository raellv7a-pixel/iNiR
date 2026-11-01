#!/usr/bin/env python3
"""Libera o Skwd e seleciona com segurança o papel de parede nativo da iNiR.

Execute somente após parar a shell da iNiR. O comando altera uma opção e salva
um backup; ele não altera branches nem restaura uma configuração antiga.
"""
import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import socket
import stat
import sys
import tempfile


def config_path():
    root = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    old, new = root / "illogical-impulse", root / "inir"
    if old.is_dir() and not (old.is_symlink() and new.is_dir()):
        return old / "config.json"
    return new / "config.json"


def socket_path():
    override = os.environ.get("SKWD_WALL_V2_SOCK")
    if override:
        return Path(override)
    return Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "skwd-wall-v2/wall.sock"


def release(path):
    with socket.socket(socket.AF_UNIX) as conn:
        conn.settimeout(45)
        conn.connect(str(path))
        conn.sendall(b'{"id":1,"method":"integration.release","params":{}}\n')
        with conn.makefile("rb") as stream:
            line = stream.readline(1024 * 1024 + 1)
        if not line or len(line) > 1024 * 1024:
            raise RuntimeError("resposta inválida do Skwd")
        response = json.loads(line)
        if response.get("id") != 1 or response.get("error") or response.get("result", {}).get("released") is not True:
            raise RuntimeError("o Skwd não confirmou que suas superfícies de papel de parede pararam")


def set_native(path):
    path = path.resolve(strict=True)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise RuntimeError("a configuração não é um arquivo comum")
    lock_path = Path(str(path) + ".lock")
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        old = path.read_bytes()
        config = json.loads(old)
        if not isinstance(config, dict):
            raise RuntimeError("a raiz da configuração precisa ser um objeto")
        iris = config.setdefault("iris", {})
        if not isinstance(iris, dict):
            raise RuntimeError("a configuração da iRiS não é um objeto")
        skwd = iris.setdefault("skwd", {})
        if not isinstance(skwd, dict):
            raise RuntimeError("a configuração do Skwd não é um objeto")
        skwd["mode"] = "native"
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup = path.with_name(path.name + ".before-skwd-restore-" + stamp)
        fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IMODE(info.st_mode))
        with os.fdopen(fd, "wb") as stream:
            stream.write(old)
            stream.flush()
            os.fsync(stream.fileno())
        temp_path = None
        try:
            fd, temp_name = tempfile.mkstemp(prefix=".skwd-restore-", dir=path.parent)
            temp_path = Path(temp_name)
            with os.fdopen(fd, "wb") as stream:
                os.fchmod(stream.fileno(), stat.S_IMODE(info.st_mode))
                stream.write((json.dumps(config, ensure_ascii=False, indent=2) + "\n").encode())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, path)
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
        return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shell-stopped", action="store_true", help="confirmar que a shell da iNiR está parada")
    args = parser.parse_args()
    if not args.shell_stopped:
        parser.error("pare a shell da iNiR antes e informe --shell-stopped")
    try:
        release(socket_path())
        backup = set_native(config_path())
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Não foi possível concluir a recuperação; confira a configuração e os backups: {error}", file=sys.stderr)
        return 1
    print(f"Skwd liberado; modo nativo selecionado. Backup da configuração: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
