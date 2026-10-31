"""Anagrafe pubblica MIM 2026/27: istituti STATALI nella sola Campania.

Non vengono usate le anagrafi delle scuole paritarie. Le sedi con lo stesso
sito sono raggruppate. Si registra la fonte ufficiale del censimento.
"""
import csv
import io
import ipaddress
import re
from datetime import datetime, timedelta
from urllib.parse import urlsplit, urlunsplit

import requests

CATALOG = 'https://dati.istruzione.it/opendata/opendata/catalogo/elements1/SCUANAGRAFESTAT20262720260901.csv'
PROVINCES = {'AV':'Avellino', 'BN':'Benevento', 'CE':'Caserta', 'NA':'Napoli', 'SA':'Salerno'}


def safe_url(value):
    v = str(value or '').strip().strip('"\'')
    if not v or v.lower() in ('nan', 'null', '-', 'n.d.', 'non disponibile'):
        return None
    if not re.match(r'^https?://', v, re.I):
        v = 'https://' + v
    try:
        p = urlsplit(v)
        h = (p.hostname or '').lower().rstrip('.')
        if p.scheme not in ('http','https') or not h or '.' not in h or '..' in h or len(h)>253 or p.username or p.password or p.port not in (None,80,443):
            return None
        try:
            ipaddress.ip_address(h)
            return None
        except ValueError:
            pass
        if h.endswith(('.local','.localhost','.internal')):
            return None
        return urlunsplit((p.scheme,p.netloc.lower(),'/', '', ''))
    except (ValueError,TypeError):
        return None


def csv_to_sites(payload):
    raw = payload.decode('utf-8-sig','replace')
    if '\ufffd' in raw[:5000]:
        raw = payload.decode('cp1252', 'replace')
    first = raw.splitlines()[0]
    delim = ';' if first.count(';') > first.count(',') else ','
    reader = csv.DictReader(io.StringIO(raw),delimiter=delim)
    headers = {h.upper().strip() for h in (reader.fieldnames or [])}
    required = {'SITOWEBSCUOLA', 'DENOMINAZIONESCUOLA'}
    if not required.issubset(headers):
        raise ValueError('Il formato del CSV ministeriale è cambiato: nessun elenco inventato')
    result = {}
    for row0 in reader:
        row = {str(k).strip().upper(): str(v or '').strip() for k,v in row0.items() if k}
        province = (row.get('PROVINCIA') or '').upper()
        code = (row.get('CODICESCUOLA') or '').upper()
        region = (row.get('REGIONE') or '').upper()
        if not ('CAMPANIA' in region or (len(code)>=2 and code[:2] in PROVINCES)):
            continue
        # No province guessed from individual city names; use code MIM.
        prefix = code[:2]
        if prefix not in PROVINCES:
            continue
        url = safe_url(row.get('SITOWEBSCUOLA'))
        if not url:
            continue
        host = urlsplit(url).hostname.removeprefix('www.')
        if host not in result:
            result[host] = {'url':url, 'provincia':PROVINCES[prefix],
                'scuola':row.get('DENOMINAZIONEISTITUTORIFERIMENTO') or row.get('DENOMINAZIONESCUOLA'),
                'codici':[], 'origine':'MIM statali 2026/27'}
        if code and code not in result[host]['codici']:
            result[host]['codici'].append(code)
    return sorted(result.values(),key=lambda r:(r['provincia'],r['url']))


def get_schools(state, stats, now):
    cached = state.get('scuole') or {}
    recent = cached.get('time','')
    sites = cached.get('items') or []
    if sites and cached.get('scope') == 'campania_statali_202627_v1':
        try:
            if datetime.fromisoformat(recent) > now - timedelta(days=30):
                return sites
        except ValueError:
            pass
    try:
        r = requests.get(CATALOG,headers={'User-Agent':'ATA-Campania-Notifiche/1.0'},timeout=(5,14))
        r.raise_for_status()
        if len(r.content)>20_000_000 or len(r.content)<100:
            raise ValueError('dimensione del catalogo MIM non valida')
        current = csv_to_sites(r.content)
        if not current:
            raise ValueError('catalogo MIM vuoto per la Campania')
        state['scuole'] = {'time':now.isoformat(), 'scope':'campania_statali_202627_v1', 'items':current}
        return current
    except Exception as e:
        stats['errori'].append('Anagrafe MIM: '+type(e).__name__+': '+str(e)[:110])
        return sites
