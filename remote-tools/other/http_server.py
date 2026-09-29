#!/usr/bin/env python3
"""HTTP file server on port 8090 for device-side downloads.

Serves from the deploy root (/opt/remote_deploy on the frps server).
The /frpc and /remote-client paths are aliases pointing to
server-deploy/files/remote-client.
"""
import http.server
import os
import sys

# Deploy root (parent of this script's directory).
os.chdir("/opt/remote_deploy")

PATH_MAP = {
    "/frpc": "/server-deploy/files/remote-client",
    "/remote-client": "/server-deploy/files/remote-client",
    "/device_install.sh": "/client-deploy/device_install.sh",
    "/device_uninstall.sh": "/client-deploy/device_uninstall.sh",
}

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path in PATH_MAP:
            self.path = PATH_MAP[self.path]
        super().do_GET()

server = http.server.HTTPServer(("", 8090), Handler)
print("HTTP server running on port 8090...")
sys.stdout.flush()
server.serve_forever()
