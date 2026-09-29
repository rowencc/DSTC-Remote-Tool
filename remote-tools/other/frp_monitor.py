#!/usr/bin/env python3
"""
remote_monitor.py — Remote Device Monitoring Page
"""

import http.server
import socketserver
import urllib.request
import json
import re
from datetime import datetime

PORT = 8091  # Monitor page port
FRPS_CLIENTS_URL = "http://127.0.0.1:7580/api/v2/clients?page=1&pageSize=100"
FRPS_PROXIES_URL = "http://127.0.0.1:7580/api/v2/proxies?page=1&pageSize=100"
FRPS_USER = "master"
FRPS_PASSWORD = "Rowen@3328"

# SVG Icons
ICON_SERVER = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6" y2="6"/><line x1="6" y1="18" x2="6" y2="18"/></svg>'
ICON_DEVICE = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>'
ICON_REFRESH = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>'
ICON_SSH = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>'
ICON_WEB = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>'
ICON_LINK = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>'
ICON_ONLINE = '<svg width="8" height="8" viewBox="0 0 8 8" fill="currentColor"><circle cx="4" cy="4" r="4"/></svg>'

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Remote Device Monitor</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; background: white; border-radius: 16px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); overflow: hidden; }
        .header { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: white; padding: 30px; text-align: center; }
        .header h1 { font-size: 28px; margin-bottom: 10px; display: flex; align-items: center; justify-content: center; gap: 12px; }
        .header p { opacity: 0.8; font-size: 14px; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; padding: 30px; background: #f8f9fa; }
        .stat-card { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center; }
        .stat-card .number { font-size: 36px; font-weight: bold; color: #667eea; }
        .stat-card .label { color: #666; margin-top: 5px; }
        .content { padding: 30px; }
        .section-title { font-size: 20px; color: #333; margin-bottom: 20px; padding-bottom: 10px; border-bottom: 2px solid #667eea; }
        .device-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .device-card { background: #f8f9fa; border-radius: 12px; padding: 20px; border-left: 4px solid #667eea; transition: transform 0.2s; }
        .device-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
        .device-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
        .device-name { font-size: 18px; font-weight: bold; color: #333; display: flex; align-items: center; gap: 8px; }
        .status-badge { padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: bold; display: flex; align-items: center; gap: 4px; }
        .status-online { background: #d4edda; color: #155724; }
        .device-info { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 15px; }
        .info-item { display: flex; flex-direction: column; }
        .info-label { font-size: 12px; color: #666; text-transform: uppercase; }
        .info-value { font-size: 14px; color: #333; font-family: 'Courier New', monospace; }
        .access-buttons { display: flex; gap: 10px; flex-wrap: wrap; }
        .btn { padding: 8px 16px; border-radius: 8px; text-decoration: none; font-size: 13px; font-weight: bold; transition: all 0.2s; cursor: pointer; border: none; color: white; display: flex; align-items: center; gap: 6px; }
        .btn-ssh { background: #28a745; }
        .btn-ssh:hover { background: #218838; }
        .btn-web { background: #007bff; }
        .btn-web:hover { background: #0069d9; }
        .refresh-info { text-align: center; color: #666; font-size: 12px; margin-top: 20px; }
        .refresh-btn { background: #667eea; color: white; border: none; padding: 8px 20px; border-radius: 8px; cursor: pointer; font-size: 14px; margin-right: 10px; display: flex; align-items: center; gap: 6px; }
        .refresh-btn:hover { background: #5a6fd6; }
        .no-devices { text-align: center; padding: 60px 20px; color: #666; }
        .no-devices .icon { font-size: 48px; margin-bottom: 20px; color: #ccc; }
        .toast { position: fixed; top: 20px; right: 20px; background: #28a745; color: white; padding: 12px 24px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); z-index: 1000; opacity: 0; transition: opacity 0.3s; }
        .toast.show { opacity: 1; }
        .server-info { padding: 20px 30px; background: #e3f2fd; border-radius: 8px; margin-bottom: 20px; }
        .server-info p { margin: 5px 0; color: #333; }
        .server-info .label { color: #666; font-size: 13px; }
        .ssh-modal { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); display: none; justify-content: center; align-items: center; z-index: 2000; }
        .ssh-modal.show { display: flex; }
        .modal-content { background: white; border-radius: 12px; padding: 30px; max-width: 600px; width: 90%; box-shadow: 0 20px 60px rgba(0,0,0,0.3); }
        .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        .modal-header h3 { color: #333; font-size: 20px; display: flex; align-items: center; gap: 8px; }
        .modal-close { background: none; border: none; font-size: 28px; cursor: pointer; color: #666; padding: 0; line-height: 1; }
        .modal-close:hover { color: #333; }
        .modal-body p { margin-bottom: 15px; color: #666; }
        .ssh-command { display: block; background: #1a1a2e; color: #00ff88; padding: 15px; border-radius: 8px; font-family: 'Courier New', monospace; font-size: 14px; word-break: break-all; margin-bottom: 15px; }
        .modal-hint { font-size: 13px; color: #888; }
        .modal-hint code { background: #f0f0f0; padding: 2px 6px; border-radius: 3px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>__ICON_SERVER__ Remote Device Monitor</h1>
            <p>Real-time online device and tunnel status</p>
        </div>
        
        <div class="stats">
            <div class="stat-card"><div class="number" id="total-devices">-</div><div class="label">Online Devices</div></div>
            <div class="stat-card"><div class="number" id="ssh-ports">-</div><div class="label">SSH Tunnels</div></div>
            <div class="stat-card"><div class="number" id="web-ports">-</div><div class="label">Web Tunnels</div></div>
            <div class="stat-card"><div class="number" id="last-refresh">-</div><div class="label">Last Refresh</div></div>
        </div>
        
        <div class="content">
            <div class="server-info" id="server-info">
                <p><span class="label">Server:</span> 111.198.61.41</p>
                <p><span class="label">Server Ports:</span> 7080 (TCP), 7580 (Dashboard)</p>
                <p><span class="label">Device Port Range:</span> 7010-7999 (SSH+Web, 2 ports per device)</p>
            </div>
            
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <div class="section-title">Device List</div>
                <div><button class="refresh-btn" onclick="refreshData()">__ICON_REFRESH__ Refresh</button></div>
            </div>
            
            <div class="device-list" id="device-list">
                <div class="no-devices"><div class="icon">__ICON_SERVER__</div><p>Loading...</p></div>
            </div>
            
            <div class="refresh-info">Auto-refresh every 30 seconds | Manual refresh: <a href="javascript:refreshData()">Click here</a></div>
        </div>
    </div>
    
    <div class="toast" id="toast">Copied!</div>
    
    <div class="ssh-modal" id="ssh-modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>__ICON_LINK__ SSH Connection Command</h3>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="modal-body">
                <p>Command copied to clipboard. Paste in your terminal to execute:</p>
                <code id="ssh-command" class="ssh-command"></code>
                <p class="modal-hint">Tip: Use <code>Ctrl+C</code> to copy, <code>Ctrl+V</code> to paste in terminal</p>
            </div>
        </div>
    </div>
    
    <script>
        function refreshData() {
            fetch('/api/devices').then(r => r.json()).then(data => renderDevices(data)).catch(e => console.error(e));
        }
        
        function renderDevices(data) {
            const container = document.getElementById('device-list');
            if (data.devices.length === 0) {
                container.innerHTML = '<div class="no-devices"><div class="icon">__ICON_SERVER__</div><p>No online devices</p></div>';
            } else {
                container.innerHTML = data.devices.map(d => `
                    <div class="device-card">
                        <div class="device-header">
                            <div class="device-name">__ICON_DEVICE__ ${escapeHtml(d.name)}</div>
                            <span class="status-badge status-online">__ICON_ONLINE__ Online</span>
                        </div>
                        <div class="device-info">
                            <div class="info-item"><span class="info-label">Device ID</span><span class="info-value">${escapeHtml(d.id)}</span></div>
                            <div class="info-item"><span class="info-label">SSH Port</span><span class="info-value">${d.ssh_port}</span></div>
                            <div class="info-item"><span class="info-label">Web Port</span><span class="info-value">${d.web_port}</span></div>
                            <div class="info-item"><span class="info-label">Proxies</span><span class="info-value">${escapeHtml(d.proxies)}</span></div>
                        </div>
                        <div class="access-buttons">
                            <a class="btn btn-ssh" href="javascript:copySSH(${d.ssh_port})">__ICON_SSH__ SSH</a>
                            <a class="btn btn-web" href="javascript:openWeb(${d.web_port})">__ICON_WEB__ Web</a>
                        </div>
                    </div>
                `).join('');
            }
            document.getElementById('total-devices').textContent = data.devices.length;
            document.getElementById('ssh-ports').textContent = data.devices.length;
            document.getElementById('web-ports').textContent = data.devices.length;
            document.getElementById('last-refresh').textContent = new Date().toLocaleTimeString();
        }
        
        function copySSH(port) {
            const cmd = `ssh -p ${port} root@111.198.61.41`;
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(cmd).then(() => {
                    document.getElementById('ssh-command').textContent = cmd;
                    document.getElementById('ssh-modal').classList.add('show');
                });
            } else {
                document.getElementById('ssh-command').textContent = cmd;
                document.getElementById('ssh-modal').classList.add('show');
                showToast('Command shown, please copy manually');
            }
        }
        function openWeb(port) {
            const url = `http://111.198.61.41:${port}`;
            window.open(url, '_blank');
        }
        function closeModal() {
            document.getElementById('ssh-modal').classList.remove('show');
        }
        function showToast(msg) {
            const t = document.getElementById('toast');
            t.textContent = msg;
            t.classList.add('show');
            setTimeout(() => t.classList.remove('show'), 2000);
        }
        function escapeHtml(t) { const d = document.createElement('div'); d.textContent = t; return d.innerHTML; }
        
        document.getElementById('ssh-modal').addEventListener('click', function(e) {
            if (e.target === this) closeModal();
        });
        
        refreshData();
        setInterval(refreshData, 30000);
    </script>
</body>
</html>
"""

# Replace placeholders with actual SVG icons
HTML_TEMPLATE = (HTML_TEMPLATE
    .replace('__ICON_SERVER__', ICON_SERVER)
    .replace('__ICON_DEVICE__', ICON_DEVICE)
    .replace('__ICON_REFRESH__', ICON_REFRESH)
    .replace('__ICON_SSH__', ICON_SSH)
    .replace('__ICON_WEB__', ICON_WEB)
    .replace('__ICON_LINK__', ICON_LINK)
    .replace('__ICON_ONLINE__', ICON_ONLINE)
)

class MonitorHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass
    
    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode('utf-8'))
        elif self.path == '/api/devices':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            devices = get_online_devices()
            self.wfile.write(json.dumps({'devices': devices, 'updated_at': datetime.now().isoformat()}, ensure_ascii=False).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

def get_online_devices():
    """Get online devices from frps API"""
    devices = []
    
    try:
        auth = f"{FRPS_USER}:{FRPS_PASSWORD}"
        import base64
        auth_header = "Basic " + base64.b64encode(auth.encode()).decode()
        
        # Get proxies list
        req = urllib.request.Request(FRPS_PROXIES_URL, headers={'Authorization': auth_header})
        with urllib.request.urlopen(req, timeout=5) as resp:
            proxies_data = json.loads(resp.read().decode())
        
        proxies = proxies_data.get('data', {}).get('items', [])
        
        # Get clients list for online status
        req = urllib.request.Request(FRPS_CLIENTS_URL, headers={'Authorization': auth_header})
        with urllib.request.urlopen(req, timeout=5) as resp:
            clients_data = json.loads(resp.read().decode())
        
        clients = {c['clientID']: c for c in clients_data.get('data', {}).get('items', [])}
        
        # Group proxies by clientID
        client_proxies = {}
        for proxy in proxies:
            client_id = proxy.get('clientID', '')
            name = proxy.get('name', '')
            port = proxy.get('spec', {}).get('tcp', {}).get('remotePort', 0)
            phase = proxy.get('status', {}).get('phase', 'offline')
            
            if not client_id or not port:
                continue
            
            if client_id not in client_proxies:
                client_proxies[client_id] = []
            
            client_proxies[client_id].append({
                'name': name,
                'port': port,
                'phase': phase
            })
        
        # Build device list (only online clients)
        for client_id, proxy_list in client_proxies.items():
            client = clients.get(client_id)
            if not client or not client.get('online', False):
                continue
            
            ssh_port = None
            web_port = None
            
            for proxy in proxy_list:
                if 'ssh' in proxy['name'].lower() or proxy['port'] % 2 == 0:
                    ssh_port = proxy['port']
                else:
                    web_port = proxy['port']
            
            if ssh_port and not web_port:
                web_port = ssh_port + 1
            elif web_port and not ssh_port:
                ssh_port = web_port - 1
            
            devices.append({
                'name': f"Device-{ssh_port}",
                'id': client_id[:8],
                'ssh_port': ssh_port or 0,
                'web_port': web_port or 0,
                'proxies': ', '.join([p['name'] for p in proxy_list])
            })
    
    except Exception as e:
        print(f"Failed to get devices: {e}")
        import traceback
        traceback.print_exc()
    
    return devices

if __name__ == '__main__':
    print(f"Remote Monitor running: http://localhost:{PORT}")
    with socketserver.TCPServer(("", PORT), MonitorHandler) as httpd:
        httpd.serve_forever()
