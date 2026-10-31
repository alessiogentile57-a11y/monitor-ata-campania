"""Monitor indipendente ATA Campania: notifica solo avvisi ufficiali AA/CS aperti.

Limiti: la scansione delle scuole è a rotazione; gli albi che richiedono JS o
accesso autenticato non sono letti. In assenza di prova della scadenza non invia.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import logging
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlsplit, urlunsplit

import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from registry import get_schools, safe_url
from detection import classify, ROME, CALL, AA, CS

ROOT = Path(__file__).parent
DATA = ROOT / 'data'
STATE_FILE = DATA / 'state.json'
LAST_FILE = DATA / 'last_run.json'
HEADERS = {'User-Agent': 'ATA-Campania-Monitor/1.0 (+ricerca avvisi istituzionali)', 'Accept-Language':'it-IT,it;q=0.8'}
MAX_SITES = 12
OFFICES = [
    ('Napoli', 'https://www.uat-napoli.it/tag/interpelli-personale-ata/'),
    ('Avellino', 'https://atavellino.it/'),
    ('Benevento', 'https://www.mim.gov.it/web/miur-usr-campania/uat-benevento'),
    ('Caserta', 'https://www.uat-caserta.it/'),
    ('Salerno', 'https://www.mim.gov.it/web/miur-usr-campania/uat-salerno'),
]
LINKCTX = re.compile(r'interpell|supplen|avvis|reclutament|candidatur|selezion|graduator|albo|personale.{0,4}ata',re.I)
SKIP_LINK = re.compile(r'login|/accesso|facebook|twitter|instagram|whatsapp|mailto:|javascript:',re.I)
OFFICIAL_SUFFIXES = ('.edu.it','.gov.it','.istruzione.it')
OFFICIAL_HOSTS = {'uat-napoli.it','www.uat-napoli.it','atavellino.it','www.atavellino.it',
                  'uat-caserta.it','www.uat-caserta.it','mim.gov.it','www.mim.gov.it',
                  'uat-salerno.it','www.uat-salerno.it','uat-benevento.it','www.uat-benevento.it'}
MONTH = lambda: datetime.now(ROME)


def load_state():
    try:
        d=json.loads(STATE_FILE.read_text(encoding='utf-8'))
        return d if isinstance(d,dict) else {}
    except (OSError,ValueError):return {}


def save_json(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
    tmp.replace(path)


def host(url):return (urlsplit(url).hostname or '').lower().removeprefix('www.')


def official_url(url,school_home=None):
    """No arbitrary external navigation: link must be a school host or known office."""
    p=urlsplit(url)
    if p.scheme not in ('https','http') or not p.hostname or p.username or p.password or p.port not in (None,80,443):return False
    h=(p.hostname or '').lower()
    if school_home and host(url)==host(school_home):return True
    return (h in OFFICIAL_HOSTS and h not in {'mim.gov.it','www.mim.gov.it'}) or (h in {'mim.gov.it','www.mim.gov.it'} and '/web/miur-usr-campania' in p.path)


def retrieve(url,home=None):
    if not official_url(url,home):raise ValueError('URL non appartenente alla scuola/ufficio autorizzato')
    r=requests.get(url,headers=HEADERS,timeout=(3,6),allow_redirects=True,stream=True)
    try:
        if not official_url(r.url,home):raise ValueError('redirect fuori dalla fonte ufficiale')
        r.raise_for_status()
        if int(r.headers.get('Content-Length') or 0)>2_000_000:
            raise ValueError('file troppo grande')
        data=bytearray()
        for chunk in r.iter_content(chunk_size=65536):
            data.extend(chunk)
            if len(data)>2_000_000:raise ValueError('risorsa troppo grande')
        content_type=r.headers.get('Content-Type','').lower()
        if 'pdf' in content_type or urlsplit(r.url).path.lower().endswith('.pdf'):
            reader=PdfReader(io.BytesIO(data),strict=False)
            parts=[]
            for p in list(reader.pages)[:6]:parts.append((p.extract_text() or '')[:6000])
            return '\n'.join(parts),[],r.url
        soup=BeautifulSoup(bytes(data),'html.parser')
        for tag in soup(['script','style','nav','footer']):tag.decompose()
        body=soup.get_text(' ',strip=True)[:40000]
        links=[]
        for a in soup.select('a[href]'):
            u=urljoin(r.url,a.get('href',''))
            if SKIP_LINK.search(u) or not official_url(u,home):continue
            anchor=a.get_text(' ',strip=True)[:220]
            context=a.parent.get_text(' ',strip=True)[:320] if a.parent else anchor
            links.append((u,anchor,context))
        return body,links,r.url
    finally:r.close()


def candidates(links):
    """Follow specific notice links only; do not assess deadline from list pages."""
    out=[];seen=set()
    for u,label,ctx in links:
        words=(label+' '+ctx).lower()
        if u in seen or not LINKCTX.search(words):continue
        if not (CALL.search(words) or AA.search(words) or CS.search(words)):
            continue
        seen.add(u);out.append(u)
    return out[:9]


def scan_school(row,now):
    home=row['url']; hits=[];stats={'pages':0,'error':None,'external':0}
    try:
        body,links,_=retrieve(home,home)
        stats['pages']+=1
        # Inspect a small number of relevant sections, then linked notices.
        sections=[]
        for u,anchor,ctx in links:
            if re.search(r'interpell|supplen|albo|circolari|avvisi|personale.{0,4}ata',anchor+' '+u,re.I):
                if u not in sections:sections.append(u)
        linkset=links[:]
        for section in sections[:2]:
            try:
                _,more,_=retrieve(section,home)
                stats['pages']+=1;linkset+=more
            except Exception:pass
        for u in candidates(linkset)[:3]:
            try:
                document,more,final=retrieve(u,home)
                stats['pages']+=1
                # If a notice page is brief and links to a direct PDF, inspect it too.
                if len(document)<1200:
                    pdfs=[p for p,a,c in more if p.lower().split('?')[0].endswith('.pdf')]
                    if pdfs:
                        try:
                            pdf_text,_,pdf_final=retrieve(pdfs[0],home)
                            stats['pages']+=1
                            if len(pdf_text)>len(document):document,final=pdf_text,pdf_final
                        except Exception:pass
                result=classify(document,now)
                if result:hits.append({**result,'url':final,'scuola':row['scuola'],'provincia':row['provincia'], 'source':'sito della scuola statale'})
            except Exception:pass
        return hits,stats
    except Exception as e:
        stats['error']=f"{home}: {type(e).__name__}: {str(e)[:100]}"
        return [],stats


def scan_office(name,url,now):
    hits=[];stat={'pages':0,'error':None}
    try:
        body,links,_=retrieve(url)
        stat['pages']+=1
        for u in candidates(links)[:8]:
            try:
                document,extra,final=retrieve(u)
                stat['pages']+=1
                # Only if AA/CS are specifically mentioned; no DSGA-only notices.
                result=classify(document,now)
                if not result:continue
                # Provincial office can repost notices from elsewhere; ensure local school cue.
                city=re.compile(r'Campania|Napoli|Avellino|Benevento|Caserta|Salerno|(?:\bNA|\bCE|\bAV|\bBN|\bSA)(?:IC|IS|EE|TF)',re.I)
                if not city.search(document[:3000]):continue
                hits.append({**result,'url':final,'scuola':'Avviso UAT - scuola da verificare nell’atto',
                             'provincia':name,'source':'Ambito territoriale ufficiale'})
            except Exception:pass
    except Exception as e:stat['error']=f'UAT {name}: {type(e).__name__}: {str(e)[:90]}'
    return hits,stat


def rss_urls():
    terms=['"interpello" "assistente amministrativo" "Campania"',
           '"interpello" "collaboratore scolastico" "Campania"']
    return ['https://www.bing.com/search?format=rss&q='+quote_plus(t) for t in terms]


def scan_rss(now):
    """Extra discovery only; never alert from RSS text, always open official notice."""
    results=[];feeds_ok=0;entries=0
    for rss in rss_urls():
        try:
            r=requests.get(rss,headers=HEADERS,timeout=(3,5));r.raise_for_status()
            parsed=ET.fromstring(r.content)
            feeds_ok+=1
            for entry in parsed.findall('.//item')[:18]:
                entries+=1
                url=entry.findtext('link') or ''
                if not official_url(url):continue
                try:
                    txt,links,final=retrieve(url)
                    classification=classify(txt,now)
                    if classification and re.search(r'Campania|Napoli|Avellino|Benevento|Caserta|Salerno',txt[:3000],re.I):
                        results.append({**classification,'url':final,'scuola':'Avviso ufficiale da verificare',
                                        'provincia':'Campania (verificare provincia)', 'source':'RSS → fonte ufficiale'})
                except Exception:pass
        except Exception:pass
    return results,feeds_ok,entries


def telegram(token,chat_id,message):
    r=requests.post('https://api.telegram.org/bot'+token+'/sendMessage',json={
        'chat_id':chat_id,'text':message,'disable_web_page_preview':True},timeout=(4,8))
    r.raise_for_status()
    if not r.json().get('ok'):raise RuntimeError('Telegram ha rifiutato il messaggio')


def chat_id(token):
    r=requests.get('https://api.telegram.org/bot'+token+'/getUpdates',timeout=(4,8));r.raise_for_status()
    updates=r.json().get('result',[])
    for u in reversed(updates):
        info=u.get('message') or u.get('channel_post') or {}
        if info.get('chat',{}).get('id'):
            print('CHAT ID:',info['chat']['id']);return
    print('Nessun messaggio trovato: apri il nuovo bot Telegram e scrivigli /start, poi riprova')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--mode',choices=['monitor','test','chat-id'],default='monitor')
    args=p.parse_args()
    token=os.environ.get('TELEGRAM_BOT_TOKEN','').strip()
    chat=os.environ.get('TELEGRAM_CHAT_ID','').strip()
    if args.mode=='chat-id':
        if not token:sys.exit('Manca il secret TELEGRAM_BOT_TOKEN')
        chat_id(token);return
    if args.mode=='test':
        if not token or not chat:sys.exit('Servono entrambi i secret Telegram')
        telegram(token,chat,'✅ Test riuscito. Monitor ATA Campania: Assistente amministrativo e Collaboratore scolastico.')
        print('Test Telegram riuscito');return
    if not token or not chat:sys.exit('Configura i secret TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID prima di avviare monitor')
    now=MONTH()
    state=load_state()
    stats={'data_ora':now.isoformat(), 'regione':'Campania',
           'province':['Avellino','Benevento','Caserta','Napoli','Salerno'],
           'solo_statali':True,'profili':['AA - Assistente amministrativo','CS - Collaboratore scolastico'],
           'regola':'SOLO avvisi ufficiali con scadenza data e ora future, accertate nel testo',
           'scuole_censite':0,'scuole_tentate':0,'scuole_lette':0,'pagine_lette':0,
           'errori_siti':0,'scuole_cursor':0, 'uffici_tentati':len(OFFICES),
           'rss_letti':0,'voci_rss':0,'candidati_verificati':0,
           'nuovi_notificati':0,'albi_js_non_coperti':True,'errori':[]}
    schools=get_schools(state,stats,now)
    stats['scuole_censite']=len(schools)
    if schools:
        cursor=int(state.get('cursor',0))%len(schools)
        selected=(schools[cursor:]+schools[:cursor])[:MAX_SITES]
        state['cursor']=(cursor+len(selected))%len(schools)
        stats['scuole_cursor']=state['cursor']
    else:selected=[]
    stats['scuole_tentate']=len(selected)
    hits=[]
    with ThreadPoolExecutor(max_workers=10) as pool:
        jobs=[pool.submit(scan_school,row,now) for row in selected]
        jobs.extend(pool.submit(scan_office,name,url,now) for name,url in OFFICES)
        for task in as_completed(jobs):
            notices,s=task.result()
            hits.extend(notices)
            stats['pagine_lette']+=s['pages']
            if s.get('error'):
                stats['errori_siti']+=1
                if len(stats['errori'])<12:stats['errori'].append(s['error'])
            elif s['pages']:stats['scuole_lette']+=1
    rss,okay,entries=scan_rss(now)
    hits.extend(rss);stats['rss_letti']=okay;stats['voci_rss']=entries
    stats['candidati_verificati']=len(hits)
    sent=state.setdefault('sent',{})
    for notice in hits:
        # Same URL & deadline => same opportunity. Revisions with new deadline may alert.
        identity=hashlib.sha256((notice['url']+'|'+notice['profilo']+'|'+notice['scadenza'].isoformat()).encode()).hexdigest()
        if identity in sent:continue
        txt=('📢 INTERPELLO ATA ATTIVO – CAMPANIA\n'
             f"Profilo: {notice['profilo']}\n"
             f"Scuola: {notice['scuola']}\n"
             f"Provincia: {notice['provincia']}\n"
             f"Scadenza: {notice['scadenza'].strftime('%d/%m/%Y alle %H:%M')} (Italia)\n"
             f"Fonte ufficiale: {notice['url']}\n"
             'Verifica i requisiti e le modalità di candidatura nell’avviso integrale.')
        try:
            telegram(token,chat,txt)
            sent[identity]=now.isoformat();stats['nuovi_notificati']+=1
        except Exception as e:
            stats['errori'].append('Telegram: '+str(e)[:120]);break
    # Limit growth: prune entries older than 180 days, preserve unexpired within limit.
    if len(sent)>2000:
        state['sent']=dict(sorted(sent.items(),key=lambda kv:kv[1],reverse=True)[:2000])
    save_json(STATE_FILE,state)
    save_json(LAST_FILE,stats)
    print(json.dumps(stats,indent=2,ensure_ascii=False))

if __name__=='__main__':main()
