# Monitor ATA Campania – solo interpelli aperti (AA e CS)

**Versione iniziale indipendente dal bot B017.** Destinato alle sole scuole statali della CAMPANIA: Avellino, Benevento, Caserta, Napoli e Salerno. Profili **AA – Assistente amministrativo** e **CS – Collaboratore scolastico (bidello)**, non assistente tecnico, non DSGA, non docenti.

## In cosa consiste davvero

- Ogni ora, a circa `:38` UTC, GitHub Actions tenta un controllo (possibili ritardi o esecuzioni saltate).
- Usa il catalogo ufficiale MIM 2026/27 delle scuole statali e seleziona solo codici meccanografici di Campania; non include paritarie.
- Controlla a rotazione un numero LIMITATO di siti scolastici per ora (12, tutte le tipologie di scuole) e i siti degli Uffici scolastici, più due ricerche RSS gratuite per trovare avvisi da verificare sulle fonti ufficiali.
- **Non invia nulla** se non sono contemporaneamente verificati: un avviso di interpello/reclutamento ufficiale, uno dei profili AA o CS, una data e un'ora esplicite di scadenza nel testo del singolo avviso, e il termine non è passato (fuso Europe/Rome). Esclude esiti, revoche, avvisi solo interni, avvisi senza scadenza certa e posti di lavoro di altro profilo.
- Telegram riceve soltanto le nuove opportunità; in assenza di nuovi avvisi verificati, rimane silenzioso.
- I registri `data/last_run.json` e `data/state.json` mostrano cosa è stato tentato, errori e segnalazioni già inviate.

**Limiti importanti:** l'assenza di notifiche non dimostra che non siano usciti interpelli. Il bot non legge gli albi che richiedono JavaScript, autenticazione o risorse non indicizzate; un PDF scansionato può non essere leggibile. Non garantisce di raggiungere tutte le scuole in una sola ora o di scoprire tutti gli interpelli. Se non si può verificare la scadenza, NON avvisa (potrebbe perciò perdere avvisi aperti). I dati ministeriali possono contenere siti vecchi. Il controllo di candidabilità definitiva dipende dai requisiti nell'atto originale.

## Configurazione (senza toccare il bot B017)

**1. Telegram.** Apri [BotFather](https://t.me/BotFather) e invia `/newbot`. Nome suggerito: `Interpelli ATA Campania`. Username suggerito: `InterpelliATACampaniaAvvisi_bot`, se disponibile. Il nome utente DEVE essere diverso dal bot B017. BotFather rilascia un **TOKEN segreto**: non condividerlo in chat, non caricarlo in file. Apri il nuovo bot Telegram e mandagli `/start` e un messaggio `ciao`.

**2. GitHub.** Con lo stesso account del bot B017, crea un **NUOVO repository PRIVATO** chiamato `monitor-ata-campania` (non sostituire quello B017). Estrai questo ZIP sul Mac, premi `⌘ + ⇧ + .` per vedere la cartella `.github`, e carica TUTTI i file e cartelle estratti in questo nuovo repository. Verifica che il file `.github/workflows/ata-campania.yml` sia presente nella sua sottocartella, non nella radice. Premi `Commit changes`.

**3. Segreti.** Nel nuovo repo: `Settings → Secrets and variables → Actions → New repository secret`:
- `TELEGRAM_BOT_TOKEN` = il token del NUOVO bot ATA (NON il vecchio token B017).

**4. Recupera il chat ID.** Apri `Actions → ATA Campania – Solo interpelli attivi → Run workflow`. Seleziona `chat-id` e avvia. Apri i log: dovrebbe apparire `CHAT ID: ...`. Se manca, invia un nuovo messaggio al nuovo bot e riprova. Aggiungi al repository il secondo secret `TELEGRAM_CHAT_ID` con il numero ottenuto. Puoi usare lo stesso Chat ID che usi per il bot B017 se entrambi devono scrivere a te, ma verifica che il nuovo bot riceva i tuoi messaggi.

**5. Test.** In Actions esegui `Run workflow` con `mode = test`. Il bot deve rispondere: `✅ Test riuscito. Monitor ATA Campania...`. È soltanto una prova del canale Telegram, non della ricerca.

**6. Ricerca vera.** In Actions esegui `Run workflow` con `mode = monitor`. Apri il log e `data/last_run.json`. Se l'esecuzione è verde, significa solo che il programma è terminato; verifica i numeri dei siti effettivamente esaminati e gli errori. Il controllo orario è già configurato per `:38 UTC`, con le limitazioni di GitHub.

## Costo e minuti GitHub

Questo programma non richiede servizi API a pagamento. **GitHub Free include 2.000 minuti/mese complessivi per i repository privati**, NON 2.000 per ciascun bot. I controlli possono consumare 1 minuto fatturato anche se durano 40 secondi. Con *due bot orari*, 744 + 744 = circa 1.488 minuti in un mese di 31 giorni se ogni esecuzione richiede non più di un minuto. Questo è un calcolo orientativo, non una garanzia. Questo workflow ha `timeout-minutes: 1` per contenere i consumi, ma una ricerca troppo lenta verrà interrotta e non sarà completata. Consulta [GitHub billing](https://github.com/settings/billing) e imposta il budget/spend limit a 0 per evitare spese oltre la quota.

## Fonti

- [MIM open data scuole statali 2026/27](https://dati.istruzione.it/opendata/opendata/catalogo/elements1/?area=Scuole)
- [UAT Napoli – Interpelli personale ATA](https://www.uat-napoli.it/tag/interpelli-personale-ata/)
- [Ambito Territoriale Avellino](https://atavellino.it/)
- [Ambito Territoriale Caserta](https://www.uat-caserta.it/)
- [USR Campania – UAT Salerno](https://www.mim.gov.it/web/miur-usr-campania/uat-salerno)

## Test

Esegui `python -m pytest -q test_monitor.py` dopo `pip install -r requirements.txt pytest`.

**Stato:** programma pronto per caricamento e test, NON già operativo sul tuo Telegram. L'ambiente locale non ha accesso a Internet: non è stato possibile fare prove in rete sui siti delle scuole, quindi potrebbero emergere incompatibilità da correggere in base ai log di GitHub.
