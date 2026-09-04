# Prompt sessione — Q1: il segnale «margine in calo» non è mai scattato

> Copia il blocco sotto come primo messaggio della nuova sessione.
> Scritto il 03/09/2026 a chiusura della sessione di quadratura dei numeri.
> **Modello: ultrathink** — è un fix a una regola di dominio (quale fonte è
> autorevole per il MOL), non trascrizione.

---

## Cosa devi fare

Il segnale «margine in calo» della pagina Catena **non è mai potuto scattare per
nessun cliente reale**. È l'esito Q1 della quadratura del 03/09, l'unico dei
quattro classificato «Bug — fix» (gli altri due sono decisioni di prodotto, il
terzo è strutturale).

Codice: `services/routers/gruppo.py:1671-1709`, blocco «Segnale 1».

## Il difetto, e la misura che lo prova

Il blocco legge **due colonne snapshot** di `margini_mensili`:
- gate `fatturato_netto > 0` (riga 1687: `if float(r.get("fatturato_netto") or 0) <= 0: continue`)
- valore `mol_perc` (riga 1689)

Entrambe sono **snapshot**, non calcolate. Per le sedi di catena non sono
valorizzate, quindi ogni mese viene scartato e il segnale non compare mai.

**Ri-misurato il 03/09 — la tabella è più precisa di quella in roadmap:**

| sede | mesi | passa gate `netto>0` | ha `mol_perc≠0` | **segnale possibile** |
|---|---|---|---|---|
| OFFSIDE SPORTS PUB | 9 | **0** | 0 | **0** |
| OVERTIME | 9 | 6 | **0** | **0** |
| SUSHILAND MARIANO | 9 | **9** | **0** | **0** |
| SUSHILAND SAN GIULIANO | 9 | **9** | **0** | **0** |
| SUSHILAND VILLA GUARDIA | 9 | **9** | **0** | **0** |
| LAND DEI SAPORI | 9 | 9 | 6 | 6 |
| TIME CAFE | 6 | 6 | 4 | 4 |
| CASATI 14 | 9 | 6 | 2 | 2 |

```sql
SELECT r.nome_ristorante, COUNT(*) AS mesi,
  COUNT(*) FILTER (WHERE COALESCE(mm.fatturato_netto,0) > 0) AS passa_gate,
  COUNT(*) FILTER (WHERE COALESCE(mm.mol_perc,0) <> 0)       AS ha_mol_perc,
  COUNT(*) FILTER (WHERE COALESCE(mm.fatturato_netto,0)>0
                     AND COALESCE(mm.mol_perc,0)<>0)          AS segnale_possibile
FROM margini_mensili mm JOIN ristoranti r ON r.id=mm.ristorante_id
GROUP BY 1 ORDER BY 5 DESC;
```

⚠️ **Attenzione, qui la roadmap è imprecisa e va corretta.** Dice «OFFSIDE: netto
0 su tutti i mesi; OVERTIME e 3 SUSHILAND: `mol_perc` 0,00 ovunque», facendo
pensare che il gate sul netto sia il problema principale. **Non è così:** le 3
SUSHILAND passano il gate su **9 mesi su 9** e cadono solo sul secondo ostacolo,
`mol_perc`. Chi corregge solo il gate non ripara niente per loro.

**Le uniche sedi con `mol_perc` valorizzato sono mono-sede** (LAND, TIME CAFE,
CASATI 14), dove il segnale di catena non gira. Da qui: **0 clienti serviti**.

## Da dove partire

**1. Non fidarti della tabella qui sopra: ri-misurala.** È la pratica che in
questo ciclo ha fatto cadere le ipotesi del prompt 5 volte su 10.

**2. La classe di bug è già stata corretta 3 volte, nello stesso file.** Non
inventare un approccio nuovo: guarda come fanno i fratelli e segui quello.
- `gruppo.py:_aggrega_sedi_mensili` (~riga 171) — punto unico condiviso da
  overview e margini-coperti, con test dedicati
  (`tests/test_gruppo_aggrega_sedi.py`, incluso «override vince sullo snapshot»)
- `gruppo.py:_applica_override_netto` (~riga 560) — compensa la RPC salute
- il segnale «ricavi mancanti» (subito sotto il blocco 1) — già corretto

**3. La regola di dominio da rispettare.** Per i clienti in «modalità mensile»
il fatturato vero vive in `ricavi_modalita_mensile`, e
`margini_mensili.fatturato_*` resta 0 o stantio. Ogni lettore deve **fondere
l'override**. OFFSIDE ha 7 mesi in modalità mensile, OVERTIME 7.

**4. `mol_perc` non basta ricalcolarlo nel segnale.** Va deciso se il segnale
calcola il MOL% dalla stessa formula viva degli altri percorsi (probabile: è
quello che fanno i 3 fratelli) o se si ripara lo snapshot. Vedi Q3 prima di
scegliere: lo snapshot ha **3 scrittori che non si parlano** e la roadmap lo
classifica «strutturale», non «da riparare a spot».

## Vincoli

- **Un presidio si prova per mutazione**, o non è un presidio. `tsc` verde e test
  verdi non provano niente (CLAUDE.md, Trappole).
- Il segnale è **codice worker**: nessun test frontend copre il rendering.
- Attenzione a non far scattare il segnale a sproposito: `_SOGLIA_MARGINE_CALO_PT`
  e la media dei 3 mesi precedenti restano come sono, salvo misura contraria.
- **Verifica l'effetto su dati veri prima di dichiarare chiuso**: quante sedi ×
  mesi accendono il segnale dopo il fix, e se il testo prodotto è sensato
  (`"Margine al X%, era Y% di media"`).

## Contesto di sessione

- Si lavora su **`main` locale**, niente branch. Push solo quando lo dice Mattia.
- **`export_openapi.py --check-drift` è ROSSO su main** da prima del 03/09
  (riordino non deterministico di due header, ~400 righe, zero contenuto
  semantico). Non è tuo: se tocchi `fastapi_worker.py` lo fai scattare comunque.
  **Va sistemato prima del prossimo push** — chiedi a Mattia se è compito tuo.
- Più sessioni in parallelo sono la norma: commit e file non tuoi sono attesi.

## Fuori scope

- **Q2** (food cost ÷lordo vs ÷netto) e **Q4** (quote riparto vs proiezione per
  centro): sono **decisioni di prodotto di Mattia**, non bug. Non «allinearle per
  coerenza».
- **Q3** (snapshot `margini_mensili` con 3 scrittori): strutturale, sessione
  propria. Qui serve solo per decidere il punto 4.
- La categorizzazione (fasi 4, 4bis, 5, 6, 8) è un piano a sé,
  `docs/piani/PIANO_CATEGORIZZAZIONE.md`.
