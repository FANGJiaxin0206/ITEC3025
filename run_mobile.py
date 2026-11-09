from pathlib import Path
import argparse
import json
import logging
import secrets
import socket
import subprocess
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from mediconfirm.mobile_server import create_app


def lan_address():
    for interface in ('en0', 'en1'):
        try:
            address = subprocess.check_output(['/usr/sbin/ipconfig', 'getifaddr', interface], stderr=subprocess.DEVNULL, timeout=2).decode().strip()
            if address:
                return address
        except (OSError, subprocess.SubprocessError):
            pass
    probe=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    try:
        probe.connect(('8.8.8.8',80))
        return probe.getsockname()[0]
    except OSError:
        return 'YOUR_COMPUTER_IP'
    finally:
        probe.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Run the local MediConfirm phone interface.')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--host',default='0.0.0.0')
    parser.add_argument('--https',action='store_true',help='Use a temporary self-signed HTTPS certificate.')
    args=parser.parse_args()
    token=secrets.token_urlsafe(24)
    app=create_app(ROOT,access_token=token)
    protocol='https' if args.https else 'http'
    print('\nMediConfirm phone interface - local testing only',flush=True)
    print(f'Computer: {protocol}://127.0.0.1:{args.port}/?access={token}',flush=True)
    print(f'Phone:    {protocol}://{lan_address()}:{args.port}/?access={token}',flush=True)
    print('Keep this terminal open. Phone and computer must share a network.',flush=True)
    print('Use Take a photo on the phone. Live browser recording requires HTTPS; typing and audio upload remain available.',flush=True)
    print('Press Ctrl+C to stop. No public hosting or real notifications.\n',flush=True)
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    app.run(host=args.host,port=args.port,debug=False,use_reloader=False,ssl_context='adhoc' if args.https else None,threaded=True)
