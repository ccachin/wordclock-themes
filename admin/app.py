import json, re, secrets, os, urllib.request, urllib.error, html, webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, parse_qs
from getpass import getpass
import credentials
import sys
from base64 import b64encode, b64decode

REPO='ccachin/wordclock-themes'
BASE='https://api.github.com/repos/'+REPO
TOKEN=''; CSRF=secrets.token_urlsafe(32); PORT=8765
CONSENT='Licence : CC0 1.0 — Je confirme être autorisé à soumettre ce thème.'
FIELDS=('name','author','description','front','rear','harmony','frontEffect','rearEffect','frontSpeed','rearSpeed')
def api(path, method='GET', data=None):
    req=urllib.request.Request(BASE+path, data=None if data is None else json.dumps(data).encode(), method=method, headers={'Authorization':'Bearer '+TOKEN,'Accept':'application/vnd.github+json','Content-Type':'application/json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'Wordclock-admin'})
    try:
        with urllib.request.urlopen(req,timeout=25) as r: return json.load(r)
    except urllib.error.HTTPError as e: raise ValueError('GitHub HTTP '+str(e.code)+': '+e.read(1000).decode(errors='replace')) from None

def validate(t):
    if type(t) is not dict or type(t.get('version')) is not int or t['version']!=2: raise ValueError('Version 2 requise')
    d={'version':2}
    for k,n in [('name',48),('author',48),('description',200)]:
        v=t.get(k,'') if k=='description' else t.get(k)
        if not isinstance(v,str) or len(v.encode())>n or (k=='name' and not v.strip()) or any(ord(c)<32 or ord(c)==127 for c in v): raise ValueError('Champ invalide : '+k)
        d[k]=v
    for k in ('front','rear'):
        if not isinstance(t.get(k),str) or not re.fullmatch('#[0-9a-fA-F]{6}',t[k]): raise ValueError('Couleur invalide')
        d[k]=t[k].upper()
    for k,allowed in [('harmony',('manual','identical','complementary','analogous-plus','analogous-minus','triadic')),('frontEffect',('solid','breathing','color-cycle')),('rearEffect',('solid','breathing','color-cycle','rainbow','chase'))]:
        if t.get(k) not in allowed: raise ValueError('Valeur invalide : '+k)
        d[k]=t[k]
    for k in ('frontSpeed','rearSpeed'):
        if type(t.get(k)) is not int or not 0<=t[k]<=100: raise ValueError('Vitesse invalide')
        d[k]=t[k]
    return d

def submission(issue):
    body=issue.get('body') or ''
    if not issue['title'].startswith('[Theme] ') or CONSENT not in body.splitlines(): raise ValueError('Consentement ou titre manquant')
    blocks=re.findall(r'^```json\s*\n(.*?)\n```\s*$',body,re.M|re.S)
    if len(blocks)!=1 or len(blocks[0].encode())>8192: raise ValueError('Un seul bloc JSON requis')
    return validate(json.loads(blocks[0]))

def catalog():
    ref=api('/git/ref/heads/main')['object']['sha']; commit=api('/git/commits/'+ref); tree=commit['tree']['sha']
    entries=api('/git/trees/'+tree+'?recursive=1')
    if entries.get('truncated'): raise ValueError('Arbre incomplet')
    files={x['path']:x for x in entries['tree'] if x['type']=='blob'}
    def read(path): return json.loads(b64decode(api('/git/blobs/'+files[path]['sha'])['content']))
    cat=read('catalog.json')
    if cat.get('format')!='wordclock-community-catalog' or cat.get('version')!=1 or not isinstance(cat.get('themes'),list): raise ValueError('Catalogue incompatible')
    return ref,tree,files,cat,read

def commit_changes(ref,tree,changes,message):
    entries=[]
    for path,obj in changes.items():
        entry={'path':path,'mode':'100644','type':'blob'}
        if obj is None: entry['sha']=None
        else: entry['content']=json.dumps(obj,ensure_ascii=False,indent=2)+'\n'
        entries.append(entry)
    newtree=api('/git/trees','POST',{'base_tree':tree,'tree':entries})['sha']
    newcommit=api('/git/commits','POST',{'message':message,'tree':newtree,'parents':[ref]})['sha']
    api('/git/refs/heads/main','PATCH',{'sha':newcommit,'force':False})

def fingerprint(t): return tuple(str(t[k]).casefold() if k in ('name','front','rear') else t[k] for k in FIELDS)
def publish(n):
    issue=api('/issues/'+str(n))
    if issue['state']!='open' or 'pull_request' in issue: raise ValueError('Issue non ouverte')
    t=submission(issue); ref,tree,files,cat,read=catalog()
    if len(cat['themes'])>=500: raise ValueError('Catalogue plein')
    for e in cat['themes']:
        if fingerprint(validate(read(e['path'])))==fingerprint(t): raise ValueError('Thème identique déjà publié')
        if e['name'].casefold()==t['name'].casefold(): raise ValueError('Nom déjà utilisé : demander un renommage')
    slug='community-'+str(n); path='themes/'+slug+'.json'
    if path in files or any(e['id']==slug for e in cat['themes']): raise ValueError('Identifiant déjà utilisé')
    t['id']=slug; cat['themes'].append({k:t[k] for k in ('id','name','author','description','front','rear')}|{'path':path})
    commit_changes(ref,tree,{path:t,'catalog.json':cat},'Publish theme from issue #'+str(n))
    try: close(n,'Thème accepté et publié dans le catalogue (déploiement Pages en attente).')
    except Exception as e: return 'Thème publié, mais issue à fermer manuellement : '+str(e)
    return 'Thème publié. GitHub Pages peut prendre quelques minutes.'

def close(n,msg):
    api('/issues/'+str(n)+'/comments','POST',{'body':msg}); api('/issues/'+str(n),'PATCH',{'state':'closed'})
def remove(slug):
    ref,tree,files,cat,read=catalog(); matches=[e for e in cat['themes'] if e['id']==slug]
    path='themes/'+slug+'.json'
    if len(matches)!=1 or not re.fullmatch('[a-z0-9-]+',slug) or matches[0]['path']!=path or path not in files: raise ValueError('Entrée incohérente')
    cat['themes'].remove(matches[0]); commit_changes(ref,tree,{path:None,'catalog.json':cat},'Remove theme '+slug)
    return 'Thème retiré du catalogue.'

def esc(v): return html.escape(str(v),quote=True)
def form(action,key,label,reason=False):
    return f'<form method="post"><input type="hidden" name="csrf" value="{CSRF}"><input type="hidden" name="action" value="{action}"><input type="hidden" name="key" value="{esc(key)}">'+('<input name="reason" required maxlength="500" placeholder="Motif du refus">' if reason else '')+f'<label><input type="checkbox" required> Confirmer</label> <button>{esc(label)}</button></form>'
def preview(t):
    return f'<div class="clock" style="border-color:{t["rear"]};color:{t["front"]}">IL EST<br>HUIT<br>HEURES</div>'
def page(notice=''):
    out='<h1>Wordclock — Administration</h1><a href="/connection">Gérer la connexion GitHub</a> · <a href="/">Actualiser</a> · <a href="https://github.com/'+REPO+'/issues" target="_blank" rel="noreferrer">Issues GitHub</a>'
    if notice: out+='<p class="notice">'+esc(notice)+'</p>'
    out+='<h2>Contributions ouvertes</h2>'
    issues=[]
    for p in range(1,21):
        batch=api('/issues?state=open&per_page=100&page='+str(p)); issues.extend(i for i in batch if 'pull_request' not in i and i['title'].startswith('[Theme] '))
        if len(batch)<100: break
    for i in issues:
        n=i['number']; out+=f'<article><h3>#{n} — {esc(i["title"])}</h3><a href="https://github.com/{REPO}/issues/{n}" target="_blank" rel="noreferrer">Lire la demande originale</a>'
        try:
            t=submission(i); out+=preview(t)+f'<p>{esc(t["name"])} — {esc(t["author"])}</p><p>{esc(t["description"])}</p><p>Format et déclaration CC0 valides. Vérifier les droits et le contenu.</p>'+form('publish',n,'Accepter et publier')
        except Exception as e: out+='<p>Non publiable : '+esc(e)+'</p>'
        out+=form('reject',n,'Refuser',True)+'</article>'
    if not issues: out+='<p>Aucune contribution en attente.</p>'
    out+='<h2>Thèmes publiés</h2>'
    _,_,_,cat,read=catalog()
    for e in cat['themes']:
        t=validate(read(e['path'])); out+='<article>'+preview(t)+'<h3>'+esc(t['name'])+'</h3><p>'+esc(t['author'])+'</p>'+form('remove',e['id'],'Retirer du catalogue')+'</article>'
    return out
class Handler(BaseHTTPRequestHandler):
    def reply(self,body,status=200):
        data=('<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Wordclock admin</title><style>body{font:16px system-ui;max-width:850px;margin:30px auto;padding:0 16px;background:#f5f5f5;color:#222}article{background:white;padding:18px;border-radius:10px;margin:12px 0;overflow:auto}form{margin:12px 0}button,input{padding:8px}button{cursor:pointer}.clock{float:right;background:#171717;border:10px solid;width:90px;height:90px;text-align:center;padding:12px;line-height:30px;margin:8px}.notice{background:white;padding:15px}a{color:#245b99}</style>'+body+'</html>').encode()
        self.send_response(status); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('X-Frame-Options','DENY'); self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"); self.end_headers(); self.wfile.write(data)
    def valid_host(self): return self.headers.get('Host')==f'127.0.0.1:{PORT}'
    def do_GET(self):
        if not self.valid_host(): return self.reply('Accès refusé',403)
        if self.path=='/connection':
            return self.reply('<h1>Connexion GitHub</h1><p>Le remplacement se fait dans le terminal au prochain lancement. La suppression arrête également la session.</p>'+form('replace','connection','Remplacer le token')+form('forget','connection','Supprimer le token enregistré')+'<a href="/">Retour</a>')
        if self.path!='/': return self.reply('Accès refusé',403)
        try: self.reply(page())
        except Exception as e: self.reply('<p>'+esc(e)+'</p><a href="/">Réessayer</a> · <a href="/connection">Gérer la connexion GitHub</a>',500)
    def do_POST(self):
        try:
            if not self.valid_host() or self.path!='/' or self.headers.get('Origin')!=f'http://127.0.0.1:{PORT}': raise ValueError('Origine refusée')
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=4096: raise ValueError('Requête invalide')
            d=parse_qs(self.rfile.read(size).decode()); get=lambda k:d[k][0]
            if not secrets.compare_digest(get('csrf'),CSRF): raise ValueError('Session invalide')
            action,key=get('action'),get('key')
            if action in ('replace','forget'):
                global TOKEN
                credentials.delete(); TOKEN=''
                self.reply('<p>Token supprimé de Windows. Relance Lancer_Admin.bat pour te reconnecter.</p>')
                self.server.stop_requested=True
                return
            if action=='publish': msg=publish(int(key))
            elif action=='reject':
                n=int(key); i=api('/issues/'+str(n)); reason=get('reason').strip()
                if i['state']!='open' or not i['title'].startswith('[Theme] ') or 'pull_request' in i or not 0<len(reason)<=500: raise ValueError('Refus invalide')
                close(n,'Contribution refusée : '+reason); msg='Contribution refusée.'
            elif action=='remove': msg=remove(key)
            else: raise ValueError('Action inconnue')
            self.reply('<p>'+esc(msg)+'</p><a href="/">Retour au catalogue</a>')
        except Exception as e: self.reply('<p>'+esc(e)+'</p><a href="/">Retour — vérifier l’état avant de réessayer</a>',400)
def verify_token():
    repo=api('')
    if repo.get('full_name','').lower()!=REPO.lower(): raise ValueError('Dépôt inattendu')
    api('/issues?state=open&per_page=1')
    api('/git/ref/heads/main')

def connect():
    global TOKEN
    TOKEN=credentials.read() or ''
    if TOKEN:
        try:
            verify_token(); return
        except ValueError as e:
            if not str(e).startswith('GitHub HTTP 401:'): raise
            print('Token expiré ou révoqué. Saisis un nouveau token.')
    TOKEN=getpass('Token GitHub : ').strip()
    if not TOKEN: raise SystemExit('Token requis')
    verify_token()
    credentials.write(TOKEN)
    print('Token enregistré dans le Gestionnaire d’identification Windows.')

if __name__=='__main__':
    try: connect()
    except Exception as e: raise SystemExit('Connexion impossible : '+str(e)) from None
    server=HTTPServer(('127.0.0.1',PORT),Handler); server.stop_requested=False
    url=f'http://127.0.0.1:{PORT}/'; print(url+' — Ctrl+C pour arrêter'); webbrowser.open(url)
    try:
        while not server.stop_requested: server.handle_request()
    except KeyboardInterrupt: pass
    finally: server.server_close(); TOKEN=''
