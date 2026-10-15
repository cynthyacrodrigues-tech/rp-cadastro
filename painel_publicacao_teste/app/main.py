import os, sqlite3, secrets, hashlib, json, io
from datetime import date, datetime, timezone
from pathlib import Path
from contextlib import contextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Header, Depends
from fastapi.responses import HTMLResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from cryptography.fernet import Fernet

BASE=Path(__file__).resolve().parent.parent
DATA=Path(os.environ.get('PAINEL_DATA_DIR',str(BASE/'data')))
DATA.mkdir(parents=True,exist_ok=True)
DB=DATA/'painel.db'
KEYFILE=DATA/'storage.key'
if not KEYFILE.exists():
    KEYFILE.write_bytes(Fernet.generate_key())
    try: os.chmod(KEYFILE,0o600)
    except OSError: pass
cipher=Fernet(KEYFILE.read_bytes())
TOKEN=os.environ.get('PAINEL_API_TOKEN')
if not TOKEN:
    raise RuntimeError('Configure PAINEL_API_TOKEN antes de iniciar. Consulte README.md.')
app=FastAPI(title='Painel Inteligente de Cadastro de Empresas',docs_url=None,redoc_url=None)
app.mount('/static',StaticFiles(directory=str(BASE/'app'/'static')),name='static')

def auth(authorization: str|None=Header(None)):
    if not authorization or not authorization.startswith('Bearer ') or not secrets.compare_digest(authorization[7:],TOKEN):
        raise HTTPException(401,'Acesso não autorizado')

@contextmanager
def conn():
    c=sqlite3.connect(DB);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON')
    try: yield c;c.commit()
    finally:c.close()
with conn() as c:
    c.executescript('''CREATE TABLE IF NOT EXISTS companies(id INTEGER PRIMARY KEY, name TEXT NOT NULL, cnpj TEXT NOT NULL UNIQUE, city TEXT NOT NULL DEFAULT 'Jataí', uf TEXT NOT NULL DEFAULT 'GO', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS certificates(id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL REFERENCES companies(id), category TEXT NOT NULL, issuer TEXT NOT NULL, status TEXT NOT NULL, issued_on TEXT, expires_on TEXT, verified_on TEXT, notes TEXT DEFAULT '', filename TEXT, encrypted_path TEXT, sha256 TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at TEXT DEFAULT CURRENT_TIMESTAMP, action TEXT NOT NULL, target TEXT NOT NULL);''')

class Company(BaseModel):
    name:str=Field(min_length=2,max_length=180)
    cnpj:str
    city:str=Field(default='Jataí',min_length=2,max_length=120)
    uf:str=Field(default='GO',min_length=2,max_length=2)
class Certificate(BaseModel):
    company_id:int
    category:str
    issuer:str=Field(min_length=2,max_length=120)
    status:str
    issued_on:date|None=None
    expires_on:date|None=None
    verified_on:date|None=None
    notes:str=Field(default='',max_length=2000)
CATEGORIES={'Municipal','Estadual','Federal (RFB/PGFN)','FGTS','Trabalhista (CNDT)','Judicial'}
STATUSES={'Não consultada','Em análise','Negativa','Positiva','Positiva com efeitos de negativa','Indisponível'}
PORTALS=[{'category':'Municipal','name':'Jataí/GO - SIGEP','url':'https://jatai.sigep.com.br/portal/city-portal.jsf','mode':'assistido'}, {'category':'Estadual','name':'Goiás - Secretaria da Economia','url':'https://www.go.gov.br/','mode':'assistido'}, {'category':'Federal (RFB/PGFN)','name':'Receita Federal / PGFN','url':'https://www.gov.br/pt-br/servicos/emitir-certidao-de-regularidade-fiscal-perante-a-fazenda-nacional','mode':'assistido'}, {'category':'FGTS','name':'Caixa - CRF','url':'https://consulta-crf.caixa.gov.br/consultacrf/pages/consultaEmpregador.jsf','mode':'assistido'}, {'category':'Trabalhista (CNDT)','name':'TST - CNDT','url':'https://www.tst.jus.br/certidao1','mode':'assistido'}, {'category':'Judicial','name':'TJGO','url':'https://www.tjgo.jus.br/','mode':'assistido'}]

def audit(c,action,target):c.execute('INSERT INTO audit(action,target) VALUES(?,?)',(action,target))
def digits(s):return ''.join(ch for ch in s if ch.isdigit())
def cnpj_valid(s):
    s=digits(s)
    if len(s)!=14 or s==s[0]*14:return False
    def dv(part,weights):return (11-sum(int(a)*b for a,b in zip(part,weights))%11)%11%10
    return int(s[12])==dv(s[:12],[5,4,3,2,9,8,7,6,5,4,3,2]) and int(s[13])==dv(s[:13],[6,5,4,3,2,9,8,7,6,5,4,3,2])

@app.get('/',response_class=HTMLResponse)
def home():return (BASE/'app'/'static'/'index.html').read_text(encoding='utf-8')
@app.get('/api/portals',dependencies=[Depends(auth)])
def portals():return PORTALS
@app.get('/api/companies',dependencies=[Depends(auth)])
def companies():
    with conn() as c:return [dict(x) for x in c.execute('SELECT * FROM companies ORDER BY name')]
@app.post('/api/companies',dependencies=[Depends(auth)])
def add_company(x:Company):
    if not cnpj_valid(x.cnpj):raise HTTPException(400,'CNPJ inválido')
    try:
        with conn() as c:
            cur=c.execute('INSERT INTO companies(name,cnpj,city,uf) VALUES(?,?,?,?)',(x.name,digits(x.cnpj),x.city,x.uf.upper()))
            audit(c,'create_company',str(cur.lastrowid));return {'id':cur.lastrowid}
    except sqlite3.IntegrityError:raise HTTPException(409,'CNPJ já cadastrado')
@app.get('/api/certificates',dependencies=[Depends(auth)])
def certificates():
    with conn() as c:return [dict(x) for x in c.execute('SELECT certificates.*, companies.name company_name, companies.cnpj FROM certificates JOIN companies ON companies.id=company_id ORDER BY certificates.id DESC')]
@app.post('/api/certificates',dependencies=[Depends(auth)])
def add_cert(x:Certificate):
    if x.category not in CATEGORIES or x.status not in STATUSES:raise HTTPException(400,'Categoria ou situação inválida')
    if x.expires_on and x.issued_on and x.expires_on<x.issued_on:raise HTTPException(400,'Validade anterior à emissão')
    with conn() as c:
        if not c.execute('SELECT 1 FROM companies WHERE id=?',(x.company_id,)).fetchone():raise HTTPException(404,'Empresa não encontrada')
        cur=c.execute('INSERT INTO certificates(company_id,category,issuer,status,issued_on,expires_on,verified_on,notes) VALUES(?,?,?,?,?,?,?,?)',(x.company_id,x.category,x.issuer,x.status,str(x.issued_on) if x.issued_on else None,str(x.expires_on) if x.expires_on else None,str(x.verified_on) if x.verified_on else None,x.notes))
        audit(c,'create_certificate',str(cur.lastrowid));return {'id':cur.lastrowid}
@app.post('/api/certificates/{cert_id}/pdf',dependencies=[Depends(auth)])
async def upload_pdf(cert_id:int,file:UploadFile=File(...)):
    if file.content_type not in ('application/pdf','application/octet-stream'):raise HTTPException(400,'Somente PDF')
    content=await file.read(10*1024*1024+1)
    if len(content)>10*1024*1024 or not content.startswith(b'%PDF-'):raise HTTPException(400,'PDF inválido ou acima de 10 MB')
    with conn() as c:
        if not c.execute('SELECT 1 FROM certificates WHERE id=?',(cert_id,)).fetchone():raise HTTPException(404,'Certidão não encontrada')
        target=DATA/(f'cert_{cert_id}_{secrets.token_hex(12)}.bin')
        target.write_bytes(cipher.encrypt(content))
        old=c.execute('SELECT encrypted_path FROM certificates WHERE id=?',(cert_id,)).fetchone()['encrypted_path']
        c.execute('UPDATE certificates SET encrypted_path=?,filename=?,sha256=? WHERE id=?',(str(target),f'certidao_{cert_id}.pdf',hashlib.sha256(content).hexdigest(),cert_id))
        audit(c,'upload_pdf',str(cert_id))
    if old:Path(old).unlink(missing_ok=True)
    return {'ok':True,'sha256':hashlib.sha256(content).hexdigest()}
@app.get('/api/certificates/{cert_id}/pdf',dependencies=[Depends(auth)])
def get_pdf(cert_id:int):
    with conn() as c:
        row=c.execute('SELECT * FROM certificates WHERE id=?',(cert_id,)).fetchone()
        if not row or not row['encrypted_path']:raise HTTPException(404,'PDF não encontrado')
        content=cipher.decrypt(Path(row['encrypted_path']).read_bytes());audit(c,'download_pdf',str(cert_id))
        return Response(content,media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="certidao_{cert_id}.pdf"','Cache-Control':'no-store'})
@app.get('/api/summary',dependencies=[Depends(auth)])
def summary():
    with conn() as c:
        companies=c.execute('SELECT COUNT(*) FROM companies').fetchone()[0]
        certs=c.execute('SELECT COUNT(*) FROM certificates').fetchone()[0]
        expiring=c.execute("SELECT COUNT(*) FROM certificates WHERE expires_on BETWEEN date('now') AND date('now','+30 days')").fetchone()[0]
        expired=c.execute("SELECT COUNT(*) FROM certificates WHERE expires_on < date('now')").fetchone()[0]
        return {'companies':companies,'certificates':certs,'expiring_30_days':expiring,'expired':expired}
