#!/usr/bin/env python3
import os,json,sqlite3,hashlib,hmac,secrets,mimetypes,urllib.parse,re,unicodedata
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from datetime import datetime,timedelta,timezone
ROOT=Path(__file__).resolve().parent; STATIC=ROOT/'static'; DB=ROOT/'data'/'zyrean.db'
HOST=os.getenv('HOST','127.0.0.1'); PORT=int(os.getenv('PORT','8787')); PAYMENT_MODE=os.getenv('PAYMENT_MODE','sandbox'); FEE=.03

def now(): return datetime.now(timezone.utc).isoformat()
def money(v): return round(float(v)+1e-9,2)
def slugify(s):
 s=unicodedata.normalize('NFKD',str(s)).encode('ascii','ignore').decode().lower(); s=re.sub(r'[^a-z0-9]+','-',s).strip('-')[:60]; return s or 'loja'
def hp(p,s=None):
 s=s or secrets.token_hex(16); return s,hashlib.pbkdf2_hmac('sha256',p.encode(),s.encode(),180000).hex()
def vp(p,s,d): return hmac.compare_digest(hp(p,s)[1],d)
def con():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c
def init():
 DB.parent.mkdir(exist_ok=True); c=con(); c.executescript("""
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,name TEXT,email TEXT UNIQUE COLLATE NOCASE,salt TEXT,phash TEXT,created_at TEXT);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,expires_at TEXT,created_at TEXT);
CREATE TABLE IF NOT EXISTS stores(id INTEGER PRIMARY KEY,user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,name TEXT,slug TEXT UNIQUE,description TEXT,accent TEXT,created_at TEXT,updated_at TEXT);
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,store_id INTEGER REFERENCES stores(id) ON DELETE CASCADE,name TEXT,description TEXT,price REAL,active INTEGER DEFAULT 1,created_at TEXT);
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY,public_id TEXT UNIQUE,store_id INTEGER REFERENCES stores(id),product_id INTEGER REFERENCES products(id),product_name TEXT,buyer_name TEXT,buyer_email TEXT,gross REAL,fee REAL,net REAL,status TEXT,payment_method TEXT,created_at TEXT,paid_at TEXT);
CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY,store_id INTEGER REFERENCES stores(id),order_id INTEGER REFERENCES orders(id),type TEXT,amount REAL,description TEXT,created_at TEXT);
CREATE TABLE IF NOT EXISTS withdrawals(id INTEGER PRIMARY KEY,store_id INTEGER REFERENCES stores(id),amount REAL,status TEXT,created_at TEXT);
"""); c.commit(); c.close()
def wallet(c,sid):
 cr=c.execute("SELECT COALESCE(SUM(amount),0) s FROM transactions WHERE store_id=? AND type='seller_credit'",(sid,)).fetchone()['s']; wd=c.execute("SELECT COALESCE(SUM(amount),0) s FROM transactions WHERE store_id=? AND type='withdrawal'",(sid,)).fetchone()['s']; fees=c.execute("SELECT COALESCE(SUM(amount),0) s FROM transactions WHERE store_id=? AND type='platform_fee'",(sid,)).fetchone()['s']; gross=c.execute("SELECT COALESCE(SUM(gross),0) s FROM orders WHERE store_id=? AND status='paid'",(sid,)).fetchone()['s']; return {'gross_sales':money(gross),'platform_fees':money(fees),'available':money(cr+wd),'withdrawn':money(abs(wd))}
class H(BaseHTTPRequestHandler):
 def log_message(self,f,*a): print('[HTTP]',f%a)
 def json(self,o,status=200,headers=None):
  b=json.dumps(o,ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(b))); self.send_header('Cache-Control','no-store');
  for k,v in (headers or {}).items(): self.send_header(k,v)
  self.end_headers(); self.wfile.write(b)
 def body(self):
  try:return json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))) or b'{}')
  except:return {}
 def cookies(self):
  d={}
  for p in self.headers.get('Cookie','').split(';'):
   if '=' in p:k,v=p.strip().split('=',1); d[k]=v
  return d
 def user(self,c):
  t=self.cookies().get('zp_session');
  if not t:return None
  return c.execute('SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires_at>?',(t,now())).fetchone()
 def need(self,c):
  u=self.user(c)
  if not u:self.json({'ok':False,'message':'Não autenticado.'},401)
  return u
 def store(self,c,uid): return c.execute('SELECT * FROM stores WHERE user_id=?',(uid,)).fetchone()
 def do_GET(self):
  u=urllib.parse.urlparse(self.path); p=u.path; q=urllib.parse.parse_qs(u.query)
  if p.startswith('/api/'):
   c=con()
   try:
    if p=='/api/health': return self.json({'ok':True,'mode':PAYMENT_MODE,'fee_rate':FEE})
    if p=='/api/me':
     x=self.user(c); return self.json({'authenticated':False} if not x else {'authenticated':True,'user':{'id':x['id'],'name':x['name'],'email':x['email']}})
    if p=='/api/dashboard':
     x=self.need(c)
     if not x:return
     s=self.store(c,x['id'])
     if not s:return self.json({'store':None,'wallet':{'gross_sales':0,'platform_fees':0,'available':0,'withdrawn':0},'products':[],'orders':[],'withdrawals':[]})
     products=[dict(r) for r in c.execute('SELECT * FROM products WHERE store_id=? ORDER BY id DESC',(s['id'],))]; orders=[dict(r) for r in c.execute('SELECT * FROM orders WHERE store_id=? ORDER BY id DESC',(s['id'],))]; wds=[dict(r) for r in c.execute('SELECT * FROM withdrawals WHERE store_id=? ORDER BY id DESC',(s['id'],))]; return self.json({'store':dict(s),'wallet':wallet(c,s['id']),'products':products,'orders':orders,'withdrawals':wds})
    if p=='/api/public/store':
     slug=(q.get('slug') or [''])[0]; s=c.execute('SELECT * FROM stores WHERE slug=?',(slug,)).fetchone()
     if not s:return self.json({'message':'Loja não encontrada.'},404)
     ps=[dict(r) for r in c.execute('SELECT id,name,description,price FROM products WHERE store_id=? AND active=1',(s['id'],))]; return self.json({'store':{'name':s['name'],'slug':s['slug'],'description':s['description'],'accent':s['accent']},'products':ps})
    return self.json({'message':'Rota não encontrada.'},404)
   finally:c.close()
  self.static(p)
 def do_POST(self):
  p=urllib.parse.urlparse(self.path).path; d=self.body(); c=con()
  try:
   if p=='/api/auth/register':
    name=str(d.get('name','')).strip(); email=str(d.get('email','')).strip().lower(); pw=str(d.get('password',''))
    if len(name)<2 or '@' not in email or len(pw)<8:return self.json({'message':'Use nome, e-mail válido e senha com 8+ caracteres.'},400)
    salt,dig=hp(pw)
    try:cur=c.execute('INSERT INTO users(name,email,salt,phash,created_at) VALUES(?,?,?,?,?)',(name,email,salt,dig,now())); c.commit(); uid=cur.lastrowid
    except sqlite3.IntegrityError:return self.json({'message':'E-mail já cadastrado.'},409)
    tok=secrets.token_urlsafe(32); exp=(datetime.now(timezone.utc)+timedelta(days=14)).isoformat(); c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(tok,uid,exp,now())); c.commit(); return self.json({'ok':True},200,{'Set-Cookie':f'zp_session={tok}; HttpOnly; SameSite=Lax; Path=/; Max-Age=1209600'})
   if p=='/api/auth/login':
    x=c.execute('SELECT * FROM users WHERE email=?',(str(d.get('email','')).strip().lower(),)).fetchone(); pw=str(d.get('password',''))
    if not x or not vp(pw,x['salt'],x['phash']):return self.json({'message':'E-mail ou senha inválidos.'},401)
    tok=secrets.token_urlsafe(32); exp=(datetime.now(timezone.utc)+timedelta(days=14)).isoformat(); c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(tok,x['id'],exp,now())); c.commit(); return self.json({'ok':True},200,{'Set-Cookie':f'zp_session={tok}; HttpOnly; SameSite=Lax; Path=/; Max-Age=1209600'})
   if p=='/api/auth/logout':
    tok=self.cookies().get('zp_session');
    if tok:c.execute('DELETE FROM sessions WHERE token=?',(tok,));c.commit()
    return self.json({'ok':True},200,{'Set-Cookie':'zp_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0'})
   x=None
   if p in ['/api/store','/api/products','/api/withdrawals']:
    x=self.need(c)
    if not x:return
   if p=='/api/store':
    name=str(d.get('name','')).strip(); slug=slugify(d.get('slug') or name); desc=str(d.get('description',''))[:800]; accent=str(d.get('accent','#0066ff'))[:20]
    if len(name)<2:return self.json({'message':'Informe o nome da loja.'},400)
    s=self.store(c,x['id'])
    if s:c.execute('UPDATE stores SET name=?,slug=?,description=?,accent=?,updated_at=? WHERE user_id=?',(name,slug,desc,accent,now(),x['id']))
    else:c.execute('INSERT INTO stores(user_id,name,slug,description,accent,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(x['id'],name,slug,desc,accent,now(),now()))
    c.commit(); return self.json({'ok':True})
   if p=='/api/products':
    s=self.store(c,x['id'])
    if not s:return self.json({'message':'Crie a loja primeiro.'},400)
    name=str(d.get('name','')).strip(); desc=str(d.get('description',''))[:800]
    try:price=money(d.get('price'))
    except:price=0
    if len(name)<2 or price<=0:return self.json({'message':'Nome e preço válidos são obrigatórios.'},400)
    c.execute('INSERT INTO products(store_id,name,description,price,created_at) VALUES(?,?,?,?,?)',(s['id'],name,desc,price,now())); c.commit(); return self.json({'ok':True})
   if p=='/api/orders':
    # public checkout: no auth required, so override earlier auth path
    pass
   if p=='/api/withdrawals':
    s=self.store(c,x['id']); amount=money(d.get('amount') or 0); w=wallet(c,s['id'])
    if amount<=0 or amount>w['available']:return self.json({'message':'Saldo insuficiente ou valor inválido.'},400)
    c.execute('INSERT INTO withdrawals(store_id,amount,status,created_at) VALUES(?,?,?,?)',(s['id'],amount,'processing',now())); c.execute('INSERT INTO transactions(store_id,type,amount,description,created_at) VALUES(?,?,?,?,?)',(s['id'],'withdrawal',-amount,'Saque solicitado',now())); c.commit(); return self.json({'ok':True})
  finally:c.close()
  # public order/payment routes reopened without auth
  if p in ['/api/orders','/api/payments/sandbox/approve']:
   c=con()
   try:
    if p=='/api/orders':
     slug=str(d.get('store_slug','')); pid=int(d.get('product_id') or 0); buyer=str(d.get('buyer_name','')).strip(); email=str(d.get('buyer_email','')).strip()
     s=c.execute('SELECT * FROM stores WHERE slug=?',(slug,)).fetchone(); prod=c.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone()
     if not s or not prod or prod['store_id']!=s['id']:return self.json({'message':'Produto inválido.'},400)
     if len(buyer)<2 or '@' not in email:return self.json({'message':'Informe nome e e-mail válidos.'},400)
     public='ZP-'+secrets.token_hex(5).upper(); gross=money(prod['price']); fee=money(gross*FEE); net=money(gross-fee)
     c.execute('INSERT INTO orders(public_id,store_id,product_id,product_name,buyer_name,buyer_email,gross,fee,net,status,payment_method,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(public,s['id'],prod['id'],prod['name'],buyer,email,gross,fee,net,'pending','pix',now())); c.commit(); return self.json({'order':{'id':public,'gross':gross,'fee':fee,'net':net},'pix_code':f'000201-ZYREAN-SANDBOX-{public}-{gross:.2f}'})
    if p=='/api/payments/sandbox/approve':
     oid=str(d.get('order_id','')); o=c.execute('SELECT * FROM orders WHERE public_id=?',(oid,)).fetchone()
     if not o:return self.json({'message':'Pedido não encontrado.'},404)
     if o['status']!='paid':
      c.execute('UPDATE orders SET status=?,paid_at=? WHERE id=?',('paid',now(),o['id'])); c.execute('INSERT INTO transactions(store_id,order_id,type,amount,description,created_at) VALUES(?,?,?,?,?,?)',(o['store_id'],o['id'],'seller_credit',o['net'],'Crédito líquido',now())); c.execute('INSERT INTO transactions(store_id,order_id,type,amount,description,created_at) VALUES(?,?,?,?,?,?)',(o['store_id'],o['id'],'platform_fee',o['fee'],'Taxa Zyrean 3%',now())); c.commit()
     return self.json({'ok':True,'gross':o['gross'],'fee':o['fee'],'net':o['net'],'wallet':wallet(c,o['store_id'])})
   finally:c.close()
  self.json({'message':'Rota não encontrada.'},404)
 def do_DELETE(self):
  p=urllib.parse.urlparse(self.path).path; c=con()
  try:
   x=self.need(c)
   if not x:return
   if p.startswith('/api/products/'):
    s=self.store(c,x['id']); pid=int(p.rsplit('/',1)[-1]); c.execute('DELETE FROM products WHERE id=? AND store_id=?',(pid,s['id'])); c.commit(); return self.json({'ok':True})
   self.json({'message':'Rota não encontrada.'},404)
  finally:c.close()
 def static(self,p):
  if p=='/':p='/index.html'
  f=(STATIC/p.lstrip('/')).resolve()
  if str(f).startswith(str(STATIC.resolve())) and f.is_file():
   b=f.read_bytes(); self.send_response(200); self.send_header('Content-Type',mimetypes.guess_type(str(f))[0] or 'application/octet-stream'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
  else:
   b=(STATIC/'index.html').read_bytes(); self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
if __name__=='__main__':
 init(); print(f'http://{HOST}:{PORT} | sandbox | taxa Zyrean 3%'); ThreadingHTTPServer((HOST,PORT),H).serve_forever()
