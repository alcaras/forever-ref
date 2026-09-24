#!/usr/bin/env python3
"""Tiny receiver: the browser hands Wowhead listview data to this and it lands in cache/wowhead/<name>.json.

Usage: python tools/recv.py [port]

Wowhead pages carry `upgrade-insecure-requests`, so fetch()/sendBeacon to http://localhost fail there.
A top-level navigation is not upgraded, so the page does:
  location.href = 'http://localhost:8790/save?name=zone-1581&data=' + encodeURIComponent(JSON.stringify(data))
"""
import os, sys, json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'cache', 'wowhead')
os.makedirs(OUT, exist_ok=True)
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8790


def save(name, body):
    name = ''.join(c for c in name if c.isalnum() or c in '-_') or 'data'
    json.loads(body)   # raises on junk
    with open(os.path.join(OUT, name + '.json'), 'wb') as f:
        f.write(body)
    print('saved', name, len(body), 'bytes', flush=True)
    return name


class H(BaseHTTPRequestHandler):
    def reply(self, code, text):
        self.send_response(code)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(text.encode('utf-8'))

    def do_POST(self):
        q = parse_qs(urlparse(self.path).query)
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        if 'application/x-www-form-urlencoded' in self.headers.get('Content-Type', ''):   # top-level form POST from the page
            form = parse_qs(body.decode('utf-8'))
            body = form.get('data', [''])[0].encode('utf-8')
            q.setdefault('name', form.get('name', ['data']))
        try:
            self.reply(200, 'saved ' + save(q.get('name', ['data'])[0], body))
        except Exception as e:
            self.reply(400, 'bad json: %s' % e)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == '/save' and 'data' in q:
            try:
                self.reply(200, 'saved ' + save(q.get('name', ['data'])[0], q['data'][0].encode('utf-8')))
            except Exception as e:
                self.reply(400, 'bad json: %s' % e)
            return
        self.reply(200, '\n'.join(sorted(os.listdir(OUT))) + '\n')

    def log_message(self, *a):
        pass


print('receiver on', PORT, '->', OUT, flush=True)
ThreadingHTTPServer(('127.0.0.1', PORT), H).serve_forever()
