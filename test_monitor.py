from datetime import datetime
from detection import classify, role, deadline, ROME
from registry import csv_to_sites, safe_url
from monitor import candidates, official_url

NOW=datetime(2026,10,31,17,0,tzinfo=ROME)

def test_aa():
    text='INTERPELLO per assistente amministrativo. Presentazione domande entro le ore 12.00 del 02/11/2026. Istituto statale Napoli.'
    r=classify(text,NOW)
    assert r and r['profilo']=='Assistente amministrativo' and r['scadenza'].day==2

def test_cs():
    t='AVVISO di reclutamento personale: collaboratore scolastico. Domande entro il giorno 3 novembre 2026 alle ore 14:30.'
    assert classify(t,NOW)['scadenza'].hour==14

def test_cs_and_aa():
    t='Interpello assistente amministrativo e collaboratore scolastico. Scadenza 01/11/2026 ore 10:00'
    assert ' e ' in classify(t,NOW)['profilo']

def test_expired():
    assert classify('Interpello collaboratore scolastico. Scadenza: 30/10/2026 ore 18:00',NOW) is None

def test_no_time():
    assert classify('Interpello per assistente amministrativo. Scadenza: 02/11/2026',NOW) is None

def test_no_deadline():
    assert classify('Interpello per collaboratore scolastico, supplenza fino al 30/06/2027',NOW) is None

def test_internal():
    assert classify('INTERPELLO INTERNO collaboratore scolastico, scadenza: 02/11/2026 ore 10:00',NOW) is None

def test_revoked():
    assert classify('INTERPELLO ANNULLATO assistente amministrativo. Scadenza: 02/11/2026 ore 10:00',NOW) is None

def test_dsga():
    assert classify('Interpello DSGA. Personale assistente amministrativo. Scadenza 02/11/2026 ore 10:00',NOW) is None

def test_not_docente():
    assert classify('Interpello per docenti ADEE, scadenza 02/11/2026 ore 10',NOW) is None

def test_specific_date_not_end_contract():
    assert classify('Interpello collaboratore scolastico, dal 31/10/2026 al 30/06/2027',NOW) is None

def test_mim_filter():
    payload=('Regione;CodiceScuola;DenominazioneScuola;SitoWebScuola\n'
             'CAMPANIA;NAIC12345X;IC Napoli;https://www.napoli.edu.it\n'
             'LOMBARDIA;MIIC12345X;IC Milano;https://www.milano.edu.it\n'
             'CAMPANIA;AVIC99999X;IC Avellino;https://www.av.edu.it\n').encode()
    res=csv_to_sites(payload)
    assert len(res)==2 and {r['provincia'] for r in res}=={'Napoli','Avellino'}

def test_broken_url():
    assert safe_url('https://www.primolevi..edu.it/') is None
    assert safe_url('http://192.168.0.1/') is None

def test_hosts():
    assert official_url('https://www.uat-napoli.it/tag/interpelli-personale-ata/')
    assert official_url('https://istituto.edu.it/avvisi/avviso-aa','https://istituto.edu.it/')
    assert not official_url('https://fake.elsewhere/avviso-aa','https://istituto.edu.it/')
    assert not official_url('https://www.mim.gov.it/some-other-region')

def test_candidate_links():
    urls=[('https://school.edu.it/1','Interpello collaboratore scolastico','Interpello CS'),
          ('https://school.edu.it/2','Consiglio di istituto','varie'),
          ('https://school.edu.it/3','Avviso assistente amministrativo','Avviso di reclutamento personale ATA')]
    assert len(candidates(urls))==2
