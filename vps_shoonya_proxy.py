#!/usr/bin/env python3
"""
Tiny Standalone Shoonya Forwarder / Proxy for VPS
Run this on your Static IP VPS:
    python vps_shoonya_proxy.py --port 8443

All requests sent from Vercel to http://YOUR_VPS_IP:8443 will be forwarded
to https://api.shoonya.com with your VPS's Whitelisted Static IP!
"""
import sys
import argparse
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler

SHOONYA_BASE = "https://api.shoonya.com"

class ShoonyaProxyHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        target_url = f"{SHOONYA_BASE}{self.path}"

        headers = {k: v for k, v in self.headers.items() if k.lower() not in ['host', 'content-length']}
        
        try:
            resp = requests.post(target_url, data=post_data, headers=headers, timeout=10)
            self.send_response(resp.status_code)
            for k, v in resp.headers.items():
                if k.lower() not in ['transfer-encoding', 'content-encoding', 'content-length']:
                    self.send_header(k, v)
            self.send_header('Content-Length', str(len(resp.content)))
            self.end_headers()
            self.wfile.write(resp.content)
        except Exception as e:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(str(e).encode('utf-8'))

    def do_GET(self):
        target_url = f"{SHOONYA_BASE}{self.path}"
        headers = {k: v for k, v in self.headers.items() if k.lower() not in ['host']}
        try:
            resp = requests.get(target_url, headers=headers, timeout=10)
            self.send_response(resp.status_code)
            for k, v in resp.headers.items():
                if k.lower() not in ['transfer-encoding', 'content-encoding', 'content-length']:
                    self.send_header(k, v)
            self.send_header('Content-Length', str(len(resp.content)))
            self.end_headers()
            self.wfile.write(resp.content)
        except Exception as e:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(str(e).encode('utf-8'))

def main():
    parser = argparse.ArgumentParser(description="Shoonya VPS Proxy")
    parser.add_argument("--port", type=int, default=8443, help="Port to listen on (default: 8443)")
    args = parser.parse_args()

    server_address = ('0.0.0.0', args.port)
    httpd = HTTPServer(server_address, ShoonyaProxyHandler)
    print(f"[*] Shoonya VPS NAT Proxy running on port {args.port}...")
    print(f"[*] Outgoing IP: Whitelisted VPS IP")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Stopping Proxy...")

if __name__ == '__main__':
    main()
