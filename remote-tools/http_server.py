#!/usr/bin/env python3
import http.server
import os
import sys

# Switch to script directory
os.chdir("/opt/remote_deploy")

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/frpc":
            self.path = "/files/remote-client"
        elif self.path == "/remote-client":
            self.path = "/files/remote-client"
        super().do_GET()

server = http.server.HTTPServer(("", 8090), Handler)
print("HTTP server running on port 8090...")
sys.stdout.flush()
server.serve_forever()
