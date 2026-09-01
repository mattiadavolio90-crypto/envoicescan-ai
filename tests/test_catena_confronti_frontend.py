"""Logica di confronto multi-sede di `(app)/catena/` — `lib/catena-confronti.ts`.

Perche' qui e non in `apps/web/`: aggiungere un runner di test a `apps/web/`
farebbe scattare `deploy-vercel.yml` (`paths: apps/web/**`) a ogni merge di un
test, cioe' un deploy di produzione per un file che non tocca il prodotto.
Il modulo TS vero viene importato da node via `tests/helpers_ts.py`.

Cosa protegge: catena/ e' la vista di gruppo, quella che aggrega piu' punti
vendita in un numero solo. La usano 2 account su 7 — i due piu' grandi del parco
(3.851.753 EUR di costi aggregati, misurati sul DB il 31/8/2026). Un errore qui
non sbaglia il numero di un cliente: sbaglia il CONFRONTO fra i suoi locali, che
e' la ragione per cui un cliente multi-sede paga il prodotto.

Diversi test qui sotto asseriscono un comportamento SBAGLIATO. Sono anomalie
fotografate, non sviste: la decisione (Mattia, 31/8) e' estrarre e coprire senza
correggere, cosi' che i fix siano una dimensione a se' con la sua finestra di
deploy. Ogni test di questo tipo dice nel nome `_fotografa_` e spiega nel corpo
cosa farebbe la versione giusta.
"""

import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/catena-confronti"

# Colonne come le definisce finestra-margini-coperti.tsx: la direzione e' per
# metrica, non globale (regola catena: NON e' sempre "numero alto = verde").
COLS = [
    {"key": "margine_perc", "label": "Margine %", "altoMeglio": True},
    {"key": "fatturato", "label": "Fatturato", "altoMeglio": True},
    {"key": "coperti", "label": "Coperti", "altoMeglio": True},
    {"key": "scontrino_medio", "label": "Scontrino medio", "altoMeglio": True},
    {"key": "mp_per_coperto", "label": "€ materia prima / coperto", "altoMeglio": False},
]


def _pv(nome, margine=None, fatturato=0, coperti=0, scontrino=None, mp=None, incompleti=False):
    return {
        "ristorante_id": f"id-{nome}",
        "nome": nome,
        "margine_perc": margine,
        "fatturato": fatturato,
        "coperti": coperti,
        "scontrino_medio": scontrino,
        "mp_per_coperto": mp,
        "dati_incompleti": incompleti,
    }


def _chiama(fn, args, richiede=None):
    return esegui_ts(
        MODULO,
        f"emit(m.{fn}(...input));",
        argomento=args,
        richiede=richiede or [fn],
    )


# ─── Soglie esportate ──────────────────────────────────────────────────────


def test_soglie_esportate_dal_modulo():
    """Le soglie sono costanti esportate, non letterali sparsi.

    Se il worker cambia il criterio del ranking, la divergenza si vede qui invece
    di restare nascosta in un `if` dentro un .tsx.
    """
    v = esegui_ts(
        MODULO,
        "emit([m.SOGLIA_MARGINE_VERDE, m.SOGLIA_MARGINE_GIALLO, m.MIN_VALORI_CONFRONTO]);",
    )
    assert v == [15, 8, 2]


# ─── margineDot: la distinzione null/0 fatta BENE ──────────────────────────


@pytest.mark.parametrize(
    "perc,atteso",
    [
        (15, "bg-emerald-500"),
        (15.1, "bg-emerald-500"),
        (14.9, "bg-amber-500"),
        (8, "bg-amber-500"),
        (7.9, "bg-rose-500"),
        (0, "bg-rose-500"),
        (-12, "bg-rose-500"),
    ],
)
def test_margine_dot_soglie(perc, atteso):
    assert _chiama("margineDot", [perc, False]) == atteso


def test_margine_dot_zero_e_null_sono_diversi():
    """0% e' un dato (rosso), null e' "non lo so" (grigio).

    E' il rovescio virtuoso del difetto ricorrente del progetto: qui la
    distinzione c'e' ed e' giusta. Il test la blinda perche' un `?? 0` di troppo
    la cancellerebbe senza che nessuno se ne accorga.
    """
    assert _chiama("margineDot", [0, False]) == "bg-rose-500"
    assert _chiama("margineDot", [None, False]) == "bg-muted-foreground/30"


def test_margine_dot_incompleti_vince_sul_valore():
    """Con dati incompleti il margine e' falso: grigio anche se il numero e' ottimo."""
    assert _chiama("margineDot", [99, True]) == "bg-muted-foreground/30"


# ─── ordinaRighe ───────────────────────────────────────────────────────────


def test_ordina_incompleti_sempre_in_fondo():
    righe = [
        _pv("incompleto", margine=99, incompleti=True),
        _pv("buono", margine=20),
        _pv("scarso", margine=3),
    ]
    out = _chiama("ordinaRighe", [righe, "margine_perc", "desc"])
    assert [r["nome"] for r in out] == ["buono", "scarso", "incompleto"]


def test_ordina_incompleti_in_fondo_anche_in_asc():
    """La coda degli incompleti non dipende dalla direzione."""
    righe = [
        _pv("incompleto", margine=1, incompleti=True),
        _pv("buono", margine=20),
        _pv("scarso", margine=3),
    ]
    out = _chiama("ordinaRighe", [righe, "margine_perc", "asc"])
    assert [r["nome"] for r in out] == ["scarso", "buono", "incompleto"]


def test_ordina_non_muta_l_array_originale():
    """`ordinaRighe` copia prima di ordinare: `data.righe` non va riordinato in
    place, o l'ordine cambierebbe sotto ad altri consumatori dello stesso array."""
    righe = [_pv("a", margine=1), _pv("b", margine=9)]
    out = esegui_ts(
        MODULO,
        "const prima = input.map(r => r.nome);"
        "m.ordinaRighe(input, 'margine_perc', 'desc');"
        "emit({prima, dopo: input.map(r => r.nome)});",
        argomento=righe,
        richiede=["ordinaRighe"],
    )
    assert out["prima"] == out["dopo"] == ["a", "b"]


def test_ordina_fotografa_null_in_coda_in_desc():
    """In `desc` i null finiscono in fondo — comportamento atteso."""
    righe = [_pv("senza", margine=None), _pv("con", margine=5)]
    out = _chiama("ordinaRighe", [righe, "margine_perc", "desc"])
    assert [r["nome"] for r in out] == ["con", "senza"]


def test_ordina_null_multipli_restano_dalla_parte_giusta():
    """Con DUE o piu' null il segno della coalescenza conta davvero.

    Con un solo null la costante non viene mai confrontata con se stessa, quindi
    -Infinity e +Infinity si comportano allo stesso modo: il null e' comunque
    l'estremo. Con due null il comparatore fa `-Inf - (-Inf)`, cioe' NaN, e
    `sort` lascia quella coppia com'e'. Un mutante che invertisse il segno
    sopravviverebbe a qualunque fixture con un solo null: e' la fixture a dover
    essere piu' ricca, non l'assert.
    """
    righe = [
        _pv("senza1", margine=None),
        _pv("medio", margine=10),
        _pv("senza2", margine=None),
        _pv("alto", margine=30),
    ]
    out = _chiama("ordinaRighe", [righe, "margine_perc", "desc"])
    assert [r["nome"] for r in out] == ["alto", "medio", "senza1", "senza2"]


def test_ordina_null_perde_anche_contro_un_margine_negativo():
    """Il null deve restare sotto un margine NEGATIVO, non scavalcarlo.

    Trovato dal code-reviewer (1/9). La coalescenza deve mandare il null sotto
    qualunque numero reale: con `?? 0` invece di `-Infinity` il null si
    posizionerebbe fra un margine positivo e uno negativo, cioe' un PV senza dato
    verrebbe mostrato come "meno peggio" di un PV che sta perdendo soldi. Un
    margine negativo in catena/ non e' teorico: Offside ha MOL negativo su tutti
    e 8 i mesi 2026.

    Le altre fixture non lo vedevano: con soli valori positivi 0 e -Infinity sono
    indistinguibili, perche' entrambi perdono contro tutto.
    """
    righe = [_pv("pos", margine=10), _pv("senza", margine=None), _pv("neg", margine=-5)]
    assert [r["nome"] for r in _chiama("ordinaRighe", [righe, "margine_perc", "desc"])] == ["pos", "neg", "senza"]


def test_ordina_fotografa_null_in_TESTA_in_asc():
    """ANOMALIA FOTOGRAFATA: in `asc` i null passano in testa.

    Causa: una sola coalescenza `null -> -Infinity` serve entrambe le direzioni,
    quindi il "non lo so" diventa il valore piu' piccolo. A schermo, ordinando
    per margine crescente, i PV senza dato scalzano il peggiore reale dalla prima
    riga. La versione giusta terrebbe i null sempre in coda come gli incompleti.
    Non corretto: cambierebbe l'ordine visibile.
    """
    righe = [_pv("senza", margine=None), _pv("con", margine=5)]
    out = _chiama("ordinaRighe", [righe, "margine_perc", "asc"])
    assert [r["nome"] for r in out] == ["senza", "con"]


# ─── calcolaExtremes: la soglia "servono almeno 2 valori" ──────────────────


def test_extremes_serve_piu_di_un_valore():
    """Con un solo PV con dato non c'e' confronto: niente evidenza.

    Regola di dominio: "il migliore" fra uno solo e' rumore, non informazione.
    """
    righe = [_pv("solo", margine=20), _pv("incompleto", margine=99, incompleti=True)]
    out = _chiama("calcolaExtremes", [righe, COLS])
    assert out["margine_perc"] == {"best": None, "worst": None}


def test_extremes_esclude_gli_incompleti_dal_confronto():
    """Un PV incompleto non puo' essere ne' il migliore ne' il peggiore."""
    righe = [
        _pv("a", margine=10),
        _pv("b", margine=20),
        _pv("gonfiato", margine=999, incompleti=True),
    ]
    out = _chiama("calcolaExtremes", [righe, COLS])
    assert out["margine_perc"] == {"best": 20, "worst": 10}


def test_extremes_ignora_i_null_ma_conta_gli_altri():
    righe = [_pv("a", margine=None), _pv("b", margine=10), _pv("c", margine=30)]
    out = _chiama("calcolaExtremes", [righe, COLS])
    assert out["margine_perc"] == {"best": 30, "worst": 10}


def test_extremes_direzione_invertita_per_mp_per_coperto():
    """REGOLA DI DOMINIO CATENA: per EUR materia prima/coperto il BASSO e' meglio.

    E' l'unica colonna con `altoMeglio: false`. Se qualcuno la "uniformasse" alle
    altre, il PV piu' efficiente verrebbe segnato in rosso e il piu' spendaccione
    in verde — un errore che a schermo sembra plausibile.
    """
    righe = [_pv("efficiente", mp=3.0), _pv("spendaccione", mp=9.0)]
    out = _chiama("calcolaExtremes", [righe, COLS])
    assert out["mp_per_coperto"] == {"best": 3.0, "worst": 9.0}
    # ...mentre su una colonna normale la direzione e' opposta:
    righe2 = [_pv("piccolo", fatturato=100), _pv("grande", fatturato=900)]
    out2 = _chiama("calcolaExtremes", [righe2, COLS])
    assert out2["fatturato"] == {"best": 900, "worst": 100}


# ─── cellTone ──────────────────────────────────────────────────────────────


def _tone(righe, col_key, nome):
    return esegui_ts(
        MODULO,
        "const ex = m.calcolaExtremes(input.righe, input.cols);"
        "const col = input.cols.find(c => c.key === input.colKey);"
        "const r = input.righe.find(x => x.nome === input.nome);"
        "emit(m.cellTone(col, r, ex));",
        argomento={"righe": righe, "cols": COLS, "colKey": col_key, "nome": nome},
        richiede=["cellTone", "calcolaExtremes"],
    )


def test_cell_tone_verde_al_migliore_rosso_al_peggiore():
    righe = [_pv("a", margine=5), _pv("b", margine=25)]
    assert "emerald" in _tone(righe, "margine_perc", "b")
    assert "rose" in _tone(righe, "margine_perc", "a")


def test_cell_tone_niente_colore_se_tutti_uguali():
    """Se best === worst nessuna cella si colora.

    Senza la guardia `v !== ex.worst` la stessa cella prenderebbe verde E rosso:
    con 4 PV allo stesso margine la tabella si accenderebbe tutta.
    """
    righe = [_pv("a", margine=10), _pv("b", margine=10)]
    assert _tone(righe, "margine_perc", "a") == ""
    assert _tone(righe, "margine_perc", "b") == ""


def test_cell_tone_intermedio_resta_neutro():
    righe = [_pv("a", margine=5), _pv("b", margine=15), _pv("c", margine=25)]
    assert _tone(righe, "margine_perc", "b") == ""


def test_cell_tone_muto_su_incompleti_e_null():
    righe = [_pv("a", margine=5), _pv("b", margine=25), _pv("x", margine=None)]
    assert _tone(righe, "margine_perc", "x") == ""
    righe2 = [_pv("a", margine=5), _pv("b", margine=25), _pv("y", margine=99, incompleti=True)]
    assert _tone(righe2, "margine_perc", "y") == ""


def test_cell_tone_incompleto_col_valore_del_migliore_resta_neutro():
    """Un PV incompleto NON si colora nemmeno quando il suo numero coincide col
    migliore dei completi.

    E' il caso che rende necessaria la guardia `if (r.dati_incompleti)`: siccome
    `calcolaExtremes` esclude gia' gli incompleti, con qualunque altro valore la
    cella resterebbe neutra da sola e la guardia sembrerebbe ridondante. Qui no:
    senza, la sede con i dati a meta' verrebbe premiata in verde per un margine
    che l'interfaccia dichiara inaffidabile.
    """
    righe = [_pv("a", margine=10), _pv("b", margine=30), _pv("incompleto", margine=30, incompleti=True)]
    assert _tone(righe, "margine_perc", "incompleto") == ""
    assert "emerald" in _tone(righe, "margine_perc", "b")


def test_cell_tone_null_non_si_colora_quando_best_e_null():
    """Con `best` a null (meno di 2 valori confrontabili) nessuna cella si
    colora, e una riga a valore null non deve farlo comunque.

    Serve a distinguere le due uscite anticipate: quella su `v == null` e quella
    su `ex.best == null`. Con una sola riga con dato la seconda basterebbe a
    coprire tutto, e la prima resterebbe non misurata.
    """
    righe = [_pv("solo", margine=20), _pv("senza", margine=None)]
    assert _tone(righe, "margine_perc", "senza") == ""
    assert _tone(righe, "margine_perc", "solo") == ""


# ─── heatStyle / cellStyle: due heatmap DIVERSE, di proposito ──────────────


def test_heat_style_spento_su_zero_null_e_max_non_positivo():
    assert _chiama("heatStyle", [None, 100]) == {}
    assert _chiama("heatStyle", [0, 100]) == {}
    assert _chiama("heatStyle", [50, 0]) == {}
    assert _chiama("heatStyle", [50, -1]) == {}


def test_heat_style_intensita_cresce_col_valore():
    basso = _chiama("heatStyle", [10, 100])["backgroundColor"]
    alto = _chiama("heatStyle", [100, 100])["backgroundColor"]
    assert basso != alto
    assert "8%" in basso   # 0.05 + 0.10*0.30 = 0.08
    assert "35%" in alto   # 0.05 + 1.00*0.30 = 0.35


def test_cell_style_spento_su_zero_e_max_non_positivo():
    assert _chiama("cellStyle", [0, 100]) == {}
    assert _chiama("cellStyle", [50, 0]) == {}


def test_le_due_heatmap_hanno_coefficienti_DIVERSI():
    """FOTOGRAFATO: `heatStyle` (0.05/0.30) e `cellStyle` (0.06/0.34) divergono.

    Due tabelle affiancate colorano lo stesso rapporto con intensita' diverse.
    Unificarle sarebbe una correzione travestita da pulizia — cambierebbe i
    colori a schermo — quindi restano due funzioni e il test dichiara la
    divergenza invece di nasconderla.
    """
    assert _chiama("heatStyle", [100, 100])["backgroundColor"] != _chiama("cellStyle", [100, 100])["backgroundColor"]
    assert "40%" in _chiama("cellStyle", [100, 100])["backgroundColor"]  # 0.06 + 0.34


# ─── calcolaHeatMax ────────────────────────────────────────────────────────


def test_heat_max_su_lista_vuota_e_zero_e_spegne_la_heatmap():
    """`Math.max(0, ...[])` da' 0, che heatStyle intercetta con `max <= 0`.

    La coppia va testata insieme: presi separatamente i due pezzi sembrano
    entrambi innocui, ed e' l'accoppiamento a garantire che nessuna cella si
    colori quando non ci sono dati.
    """
    out = _chiama("calcolaHeatMax", [[]])
    assert out == {"fatturato": 0, "coperti": 0}
    assert _chiama("heatStyle", [10, out["fatturato"]]) == {}


def test_heat_max_prende_il_massimo_per_colonna():
    righe = [_pv("a", fatturato=100, coperti=10), _pv("b", fatturato=900, coperti=5)]
    assert _chiama("calcolaHeatMax", [righe]) == {"fatturato": 900, "coperti": 10}


def test_heat_max_fotografa_null_appiattito_a_zero():
    """FOTOGRAFATO: il `?? 0` non distingue "nessun dato" da "zero".

    Su un massimo e' innocuo (0 non vince mai contro un positivo), ma se tutti i
    valori fossero null il massimo sarebbe 0 e la heatmap si spegnerebbe invece
    di dichiarare l'assenza di dati.
    """
    righe = [_pv("a", fatturato=None), _pv("b", fatturato=None)]
    assert _chiama("calcolaHeatMax", [righe])["fatturato"] == 0


# ─── pvPiuCaro ─────────────────────────────────────────────────────────────


def _row(per_pv, totale=0.0, inc=0.0):
    return {"dim_val": "Carne", "per_pv": per_pv, "totale": totale, "incidenza_pct": inc}


PV3 = [{"id": "a", "nome": "A"}, {"id": "b", "nome": "B"}, {"id": "c", "nome": "C"}]


def test_pv_piu_caro_niente_evidenza_con_un_solo_pv_che_spende():
    """Con un solo PV che ha speso, "il piu' caro" e' ovvio: sarebbe rumore."""
    assert _chiama("pvPiuCaro", [_row({"a": 500.0}), PV3]) is None


def test_pv_piu_caro_con_almeno_due():
    assert _chiama("pvPiuCaro", [_row({"a": 100.0, "b": 500.0}), PV3]) == "b"


def test_pv_piu_caro_ignora_gli_zero_e_gli_assenti():
    """Uno zero non conta come "ha speso": resta un solo PV, niente evidenza."""
    assert _chiama("pvPiuCaro", [_row({"a": 500.0, "b": 0.0}), PV3]) is None


def test_pv_piu_caro_fotografa_il_tie_break_implicito():
    """FOTOGRAFATO: a parita' di importo vince il PRIMO nell'ordine di `pv`.

    Il `>` stretto nel reduce non e' una scelta dichiarata: l'evidenza dipende
    dall'ordine con cui il worker restituisce i punti vendita. Con due sedi a
    pari spesa il triangolino si posa sempre sulla stessa, e non e' "la piu'
    cara": e' la prima della lista.
    """
    assert _chiama("pvPiuCaro", [_row({"a": 500.0, "b": 500.0}), PV3]) == "a"
    pv_invertiti = [{"id": "b", "nome": "B"}, {"id": "a", "nome": "A"}]
    assert _chiama("pvPiuCaro", [_row({"a": 500.0, "b": 500.0}), pv_invertiti]) == "b"


# ─── calcolaMaxCell / incidenzaPct ─────────────────────────────────────────


def test_max_cell_su_pivot_vuota():
    assert _chiama("calcolaMaxCell", [[], PV3]) == 0


def test_max_cell_attraversa_righe_e_pv():
    rows = [_row({"a": 10.0, "b": 50.0}), _row({"a": 900.0})]
    assert _chiama("calcolaMaxCell", [rows, PV3]) == 900.0


def test_incidenza_pct_normale():
    assert _chiama("incidenzaPct", [25.0, 100.0]) == 25.0


def test_incidenza_pct_fotografa_zero_invece_di_nessun_dato():
    """FOTOGRAFATO: con `grand_total` a 0 restituisce 0, non null.

    A schermo diventa "0,0%", che afferma "questo PV incide zero" dove il dato in
    realta' non esiste. La versione onesta darebbe null -> "—", come fanno le
    altre celle dell'area quando il dato manca.
    """
    assert _chiama("incidenzaPct", [0.0, 0.0]) == 0
    assert _chiama("incidenzaPct", [50.0, 0.0]) == 0


# ─── intervalloMese ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "anno,mese,atteso_a",
    [
        (2026, 1, "2026-01-31"),
        (2026, 2, "2026-02-28"),
        (2024, 2, "2024-02-29"),   # bisestile
        (2000, 2, "2000-02-29"),   # bisestile secolare (divisibile per 400)
        (1900, 2, "1900-02-28"),   # NON bisestile (divisibile per 100, non per 400)
        (2026, 4, "2026-04-30"),
        (2026, 12, "2026-12-31"),
    ],
)
def test_intervallo_mese_ultimo_giorno(anno, mese, atteso_a):
    """L'ultimo giorno viene da `new Date(anno, mese, 0)`, non da una tabella:
    28/29/30/31 e le regole dei bisestili secolari sono gestite dal motore."""
    out = _chiama("intervalloMese", [anno, mese])
    assert out["data_a"] == atteso_a


def test_intervallo_mese_zero_padding():
    """Senza padStart la query partirebbe con "2026-1-1", che il backend rifiuta."""
    assert _chiama("intervalloMese", [2026, 3]) == {"data_da": "2026-03-01", "data_a": "2026-03-31"}


@pytest.mark.parametrize("tz", ["Pacific/Kiritimati", "Pacific/Niue", "UTC", "Europe/Rome"])
def test_intervallo_mese_indipendente_dal_fuso(tz):
    """`new Date(anno, mese, 0)` costruisce una data LOCALE e ne legge il giorno
    locale: nessuna conversione UTC di mezzo, quindi il risultato non cambia col
    fuso. Provato sui due estremi (+14 e -11), dove un errore di conversione
    sposterebbe il giorno."""
    out = esegui_ts(
        MODULO,
        "emit(m.intervalloMese(input[0], input[1]));",
        argomento=[2026, 2],
        tz=tz,
        richiede=["intervalloMese"],
    )
    assert out == {"data_da": "2026-02-01", "data_a": "2026-02-28"}


# ─── calcolaSparkline ──────────────────────────────────────────────────────


def _punti(*mol, da_mese=1):
    return [{"mese": da_mese + i, "mol": v} for i, v in enumerate(mol)]


def test_sparkline_serve_piu_di_un_punto():
    """Un punto solo non e' un andamento; e protegge la divisione per `n - 1`."""
    assert _chiama("calcolaSparkline", [_punti(100)]) is None
    assert _chiama("calcolaSparkline", [[]]) is None


def test_sparkline_variazione_e_colore_in_salita():
    out = _chiama("calcolaSparkline", [_punti(100.0, 150.0)])
    assert out["ytdPct"] == 50.0
    assert out["su"] is True
    assert "emerald" in out["stroke"]


def test_sparkline_variazione_e_colore_in_discesa():
    out = _chiama("calcolaSparkline", [_punti(200.0, 100.0)])
    assert out["ytdPct"] == -50.0
    assert out["su"] is False
    assert "rose" in out["stroke"]


def test_sparkline_serie_piatta_non_divide_per_zero():
    """`range = max - min || 1` evita lo 0/0: senza, ogni y sarebbe NaN e il path
    SVG risulterebbe vuoto (grafico invisibile, nessun errore in console)."""
    out = _chiama("calcolaSparkline", [_punti(100.0, 100.0, 100.0)])
    assert "NaN" not in out["d"]
    assert out["ytdPct"] == 0.0
    assert out["su"] is True


def test_sparkline_etichette_mesi():
    out = _chiama("calcolaSparkline", [_punti(1.0, 2.0, 3.0, da_mese=1)])
    assert (out["meseDa"], out["meseA"]) == ("gen", "mar")


def test_sparkline_path_e_punto_finale_coerenti():
    """`cx`/`cy` escono dalla stessa geometria del path: il cerchio non puo'
    staccarsi dalla fine della linea, che era il rischio di tenere due copie
    della formula (una nel modulo, una nel componente)."""
    out = _chiama("calcolaSparkline", [_punti(0.0, 100.0)])
    ultimo_punto = out["d"].split(" ")[-1].removeprefix("L")
    assert ultimo_punto == f"{out['cx']:.1f},{out['cy']:.1f}"


def test_sparkline_geometria_assoluta():
    """Le coordinate del path in ASSOLUTO, non solo coerenti fra loro.

    Trovato dal code-reviewer (1/9): `test_sparkline_path_e_punto_finale_coerenti`
    verifica che `cx`/`cy` combacino con la fine di `d`, ma un `d` sbagliato in
    modo coerente passerebbe comunque — PAD ignorato, asse y capovolto o `M`
    iniziale perso restavano invisibili. Qui i numeri sono attesi uno per uno.

    Geometria: W=240, H=40, PAD=4. x va da 4 a 236; y e' INVERTITO (SVG cresce
    verso il basso), quindi il MOL massimo sta a y=4 e il minimo a y=36.
    """
    out = _chiama("calcolaSparkline", [_punti(0.0, 100.0, 50.0)])
    assert out["d"] == "M4.0,36.0 L120.0,4.0 L236.0,20.0"
    assert (out["cx"], out["cy"]) == (236.0, 20.0)


def test_sparkline_fotografa_rosso_su_mol_negativo_in_RISALITA():
    """ANOMALIA FOTOGRAFATA — la piu' notevole dell'area.

    Con `primo <= 0` la variazione non e' calcolabile (`ytdPct = null`), ma `su`
    diventa false e la linea esce ROSSA "in calo" mentre il MOL sta MIGLIORANDO.
    Il badge % e' nascosto, quindi a schermo resta solo il colore — che mente.

    Oggi nessun cliente la vede: `services/routers/gruppo.py:873` tiene solo i
    mesi con `netto > 0`, e con `tot_lordo <= 0` il livello e' "nessuno", che in
    `sintesi-catena.tsx:318` non renderizza affatto la sparkline. Il difetto e'
    reale ma non raggiungibile: si arma se quel filtro cambia. I valori qui sotto
    sono quelli veri di Offside (gennaio -> agosto 2026).
    """
    out = _chiama("calcolaSparkline", [_punti(-74031.50, -19221.87)])
    assert out["ytdPct"] is None
    assert out["su"] is False
    assert "rose" in out["stroke"]   # sta risalendo, ma la linea e' rossa


def test_sparkline_fotografa_null_anche_partendo_da_zero():
    """Stessa causa: `primo > 0` esclude anche lo zero esatto."""
    out = _chiama("calcolaSparkline", [_punti(0.0, 5000.0)])
    assert out["ytdPct"] is None
    assert out["su"] is False


# ─── tintConti ─────────────────────────────────────────────────────────────


def test_tint_verde_con_mol_positivo_e_dati_completi():
    assert _chiama("tintConti", [{"mol": 1000.0, "livello_dati": "completo"}]) == "verde"


def test_tint_rosso_con_mol_negativo_e_dati_completi():
    assert _chiama("tintConti", [{"mol": -1000.0, "livello_dati": "completo"}]) == "rosso"


def test_tint_zero_conta_come_positivo():
    assert _chiama("tintConti", [{"mol": 0, "livello_dati": "completo"}]) == "verde"


@pytest.mark.parametrize("livello", ["food", "nessuno"])
def test_tint_giallo_quando_i_dati_non_bastano(livello):
    """Con dati incompleti il MOL e' falso: niente verde/rosso, card neutra.

    Vale anche con un MOL vistosamente positivo: e' proprio il numero gonfiato
    che non va certificato in verde.
    """
    assert _chiama("tintConti", [{"mol": 999999.0, "livello_dati": livello}]) == "giallo"


def test_tint_fotografa_il_default_ottimista_sul_campo_assente():
    """ANOMALIA FOTOGRAFATA: campo assente -> "completo", l'ipotesi PIU' ottimista.

    Se il worker smettesse di mandare `livello_dati` (deploy parziale, campo
    rinominato), la card certificherebbe in verde un MOL che nessuno ha
    verificato. La scelta prudente sarebbe il giallo. `GruppoKpi` dichiara il
    campo non-nullable, quindi TypeScript non vedrebbe mai il caso: la difesa e'
    solo a runtime, ed e' tarata dalla parte sbagliata.
    """
    assert _chiama("tintConti", [{"mol": 1000.0}]) == "verde"
    assert _chiama("tintConti", [{"mol": 1000.0, "livello_dati": None}]) == "verde"


# ─── offsetAnello ──────────────────────────────────────────────────────────


def test_offset_anello_estremi_e_meta():
    r = 20
    circonferenza = 2 * 3.141592653589793 * r
    assert _chiama("offsetAnello", [0, r]) == pytest.approx(circonferenza)
    assert _chiama("offsetAnello", [100, r]) == pytest.approx(0.0)
    assert _chiama("offsetAnello", [50, r]) == pytest.approx(circonferenza / 2)


@pytest.mark.parametrize("fuori", [-30, 130, 1000])
def test_offset_anello_clampa_i_valori_fuori_scala(fuori):
    """Un indice fuori da 0-100 non deve disegnare un arco fuori dal cerchio."""
    r = 20
    circonferenza = 2 * 3.141592653589793 * r
    out = _chiama("offsetAnello", [fuori, r])
    assert 0 <= out <= circonferenza + 1e-9


# ─── rigaExtremes: direzione fissa, il basso e' meglio ─────────────────────


def _riga_spreco(*valori):
    return {
        "categoria": "Carne",
        "per_pv": [{"ristorante_id": f"pv{i}", "valore": v} for i, v in enumerate(valori)],
        "media_gruppo": None,
    }


def test_riga_extremes_il_basso_e_il_migliore():
    """Meno materia prima per coperto = meno spreco = meglio. Direzione OPPOSTA
    a quella delle colonne normali, ed e' il punto dell'intera finestra."""
    assert _chiama("rigaExtremes", [_riga_spreco(3.0, 9.0, 6.0)]) == {"best": 3.0, "worst": 9.0}


def test_riga_extremes_serve_piu_di_un_valore():
    assert _chiama("rigaExtremes", [_riga_spreco(5.0)]) == {"best": None, "worst": None}
    assert _chiama("rigaExtremes", [_riga_spreco(5.0, None)]) == {"best": None, "worst": None}


def test_riga_extremes_ignora_i_null():
    assert _chiama("rigaExtremes", [_riga_spreco(None, 4.0, 8.0)]) == {"best": 4.0, "worst": 8.0}


# ─── messaggioFattureDaCollocare ───────────────────────────────────────────


def test_messaggio_assente_quando_non_c_e_nulla_da_collocare():
    """null (non stringa vuota): in JSX una stringa vuota e' comunque un nodo, e
    la riga con l'icona apparirebbe vuota."""
    assert _chiama("messaggioFattureDaCollocare", [{}]) is None
    assert _chiama("messaggioFattureDaCollocare", [{"n_fatture_da_collocare": 0}]) is None


def test_messaggio_singolare_con_imperativo():
    out = _chiama("messaggioFattureDaCollocare", [{"n_fatture_da_collocare": 1}])
    assert out.startswith("C'è 1 fattura")
    assert "assegnala" in out


def test_messaggio_plurale_con_imperativo():
    out = _chiama("messaggioFattureDaCollocare", [{"n_fatture_da_collocare": 3}])
    assert out.startswith("Ci sono 3 fatture")
    assert "assegnale" in out


@pytest.mark.parametrize("n,inizio", [(1, "In tutto c'è 1 fattura"), (4, "In tutto ci sono 4 fatture")])
def test_messaggio_senza_imperativo_se_la_narrativa_ha_gia_parlato(n, inizio):
    """Se il briefing ha gia' aperto con "sono arrivate N fatture", qui basta il
    totale: ripetere "assegnale" due volte nella stessa schermata suona un
    rimprovero."""
    out = _chiama("messaggioFattureDaCollocare", [{"n_fatture_da_collocare": n, "n_fatture_arrivate_ieri": 2}])
    assert out.startswith(inizio)
    assert "assegna" not in out


@pytest.mark.parametrize("ieri", [0, None])
def test_messaggio_torna_all_imperativo_se_ieri_non_e_arrivato_nulla(ieri):
    """0 e null sono entrambi "ieri niente": la narrativa non ne ha parlato,
    quindi l'istruzione va ripetuta qui."""
    out = _chiama("messaggioFattureDaCollocare", [{"n_fatture_da_collocare": 2, "n_fatture_arrivate_ieri": ieri}])
    assert "assegnale" in out
