from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json,threading
EVENTS=[]; LOCK=threading.Lock()
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args): pass
 def do_GET(self):
  with LOCK: body=json.dumps(EVENTS if self.path=='/events' else {'ok':True}).encode()
  self.send_response(200); self.send_header('Content-Type','application/json'); self.end_headers(); self.wfile.write(body)
 def do_POST(self):
  body=self.rfile.read(int(self.headers.get('Content-Length','0')))
  value=json.loads(body)
  with LOCK: EVENTS.append(value)
  self.send_response(200); self.end_headers(); self.wfile.write(b'ok')
ThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever()
