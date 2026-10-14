"""Wait inside the admitted scope before executing a managed command."""
import os
import socket
import sys


def main():
    args = sys.argv[1:]
    if len(args) < 4 or args[0] != '--socket' or args[2] != '--':
        return 75
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(35)
            client.connect(args[1])
            if client.recv(2) != b'1':
                return 75
        os.execv(args[3], args[3:])
    except (OSError, ValueError):
        return 75


if __name__ == '__main__':
    raise SystemExit(main())
