"""Filtro conservativo: esclusivamente interpelli AA/CS con termine certo e futuro."""
import re
from datetime import datetime
from zoneinfo import ZoneInfo

ROME = ZoneInfo('Europe/Rome')
AA = re.compile(r'\bassistente\s+amministrativ[oaie]\b|\b(?:profilo|posto)\s+(?:di\s+)?AA\b', re.I)
CS = re.compile(r'\bcollaborator[ei]\s+scolastic[ioaie]\b|\b(?:profilo|posto)\s+(?:di\s+)?CS\b|\bbidell[oaie]\b', re.I)
# Exclude cases where CS is part of "collaboratore scolastico tecnico".
CS_TECH = re.compile(r'collaborator[ei]\s+scolastic[ioaie]\s+tecnic[ioaie]', re.I)
CALL = re.compile(r'interpell|avviso\s+(?:pubblico\s+)?(?:di\s+)?(?:selezione|reclutamento|supplenza)|reclutamento\s+personale|supplenza\s+breve', re.I)
CLOSED = re.compile(r'\b(?:revoc[ao]|annullat[oaie]|procedura\s+conclusa|interpello\s+chiuso|graduatoria\s+definitiva|esito\s+(?:dell.|di\s+un\s+)?interpello|definizione\s+(?:dell.|di\s+un\s+)?interpello)\b',re.I)
INTERNAL = re.compile(r'\b(?:interpello\s+interno|avviso\s+interno|riservat[oa]\s+(?:esclusivamente\s+)?al\s+personale\s+interno)\b',re.I)
NOISE = re.compile(r'\b(?:dsga|direttore\s+dei\s+servizi|assistente\s+tecnico|personale\s+docente)\b', re.I)
DEADLINE_LEAD = re.compile(
    r'\b(?:scadenza\b|(?:domand[ea]|candidat\w*|istanz[ea]|richiest[ea]|disponibilit[àa])[^.\n]{0,65}?\bentro\b|\bentro\s+(?:e\s+non\s+oltre|le\s+ore|il\s+giorno)\b|termine\s+(?:ultimo\s+)?(?:per\s+la\s+presentazione|di\s+presentazione))',
    re.I)

DATE = re.compile(r'(?<!\d)(0?[1-9]|[12]\d|3[01])[\./-](0?[1-9]|1[012])[\./-](20\d\d)(?!\d)')
MONTHS = {"gennaio":1,"febbraio":2,"marzo":3,"aprile":4,"maggio":5,"giugno":6,"luglio":7,"agosto":8,"settembre":9,"ottobre":10,"novembre":11,"dicembre":12}
WORDS = re.compile(r'(?<!\d)(0?[1-9]|[12]\d|3[01])\s+(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\s+(20\d\d)',re.I)
HOUR = re.compile(r'\bore\s*(\d{1,2})\s*[:\.,]\s*(\d{2})\b|\bore\s*(\d{1,2})\b',re.I)


def role(text):
    aa=bool(AA.search(text))
    cs=bool(CS.search(CS_TECH.sub(' ',text)))
    if not aa and not cs: return None
    return 'Assistente amministrativo e collaboratore scolastico' if aa and cs else 'Assistente amministrativo' if aa else 'Collaboratore scolastico'


def deadline(text,now=None):
    now=now or datetime.now(ROME)
    if now.tzinfo is None:now=now.replace(tzinfo=ROME)
    # Never treat dates of employment as deadlines. Require explicit keyword window.
    for m in DEADLINE_LEAD.finditer(text):
        phrase=text[m.start():m.end()+170]
        d=DATE.search(phrase) or WORDS.search(phrase)
        if not d: continue
        try:
            if d.re==DATE:
                day,month,year=map(int,d.groups())
            else:
                day=int(d.group(1));month=MONTHS[d.group(2).lower()];year=int(d.group(3))
            hh=HOUR.search(phrase)
            if not hh:continue # no hour = time ambiguous; do not notify
            h=int(hh.group(1) or hh.group(3));minute=int(hh.group(2) or 0)
            dt=datetime(year,month,day,h,minute,tzinfo=ROME)
            if dt>now and (dt-now).days<125: return dt
        except (ValueError,TypeError):
            continue
    return None


def classify(text, now=None):
    # This text must be extracted from the specific official notice, never a whole listing page.
    body=re.sub(r'\s+',' ',text or '').strip()
    if not body or not CALL.search(body) or INTERNAL.search(body):return None
    if CLOSED.search(body[:1500]):return None
    position=role(body)
    if not position:return None
    # An explicit other role in the title is a strong rejection (DSGA etc.).
    head=body[:220]
    if NOISE.search(head):
        return None
    end=deadline(body,now)
    if not end:return None
    return {'profilo':position,'scadenza':end}
