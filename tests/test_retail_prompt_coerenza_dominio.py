"""Il prompt retail deve rispettare le stesse regole di dominio di quello food.

`tests/test_prompt_ai_coerenza_dominio.py` presidia `PROMPT_CLASSIFICAZIONE_AI`
dal 29/8/2026 (il prompt vietava all'AI "Da Classificare", la negazione esatta
della regola #1 di CLAUDE.md). Il prompt retail nasce oggi: senza la stessa rete
puo' ripetere lo stesso errore in silenzio, e per un negozio e' peggio — non ha
ne' dizionario ne' safety net a valle (RETAIL_FASI.md 1.3/1.4), quindi il prompt
e' l'unica fonte di categoria oltre alla memoria locale del cliente.

Quel file NON si tocca: questi test sono la sua copia sul testo retail, piu' i
vincoli che valgono solo per il retail (nessuna categoria food, nessuna
categoria fuori dalle 5 ammesse).
"""

import re

import pytest

from config.constants import (
    CATEGORIA_ARTICOLO_DI_VENDITA,
    CATEGORIA_NON_CLASSIFICATA,
    CATEGORIE_FOOD_BEVERAGE,
    CATEGORIE_SPESE_GENERALI,
    SETTORE_RETAIL,
)
from config.prompt_ai_potenziato import (
    PROMPT_CLASSIFICAZIONE_AI,
    PROMPT_CLASSIFICAZIONE_RETAIL,
    get_prompt_classificazione,
)


# ── i 6 presidi di dominio, sul testo retail ─────────────────────────────────

def test_il_prompt_retail_non_vieta_la_categoria_di_dominio():
    """Nessuna riga deve dichiarare "Da Classificare" una risposta non valida.

    Il regex del test food (`test_prompt_ai_coerenza_dominio.py`) cercava
    "NON è MAI" con la e accentata. Non gli sfuggiva ogni divieto con apostrofo
    — l'alternativa "MAI una risposta" non ha accenti e ne intercettava una
    parte — ma bastava "NON e' MAI valida" per passargli davanti col verde:
    reggeva per caso, non per costruzione. Misurato mutando questo prompt.
    Qui la riga si normalizza e gli spazi sono elastici, cosi' né la grafia
    dell'accento né la spaziatura decidono se il presidio vede o no.
    """
    def _normalizza(riga: str) -> str:
        for accentata, piana in (("è", "e"), ("é", "e"), ("à", "a"), ("ò", "o")):
            riga = riga.replace(accentata, piana)
        return riga.replace("'", "").replace("`", "")

    divieti = [
        riga.strip() for riga in PROMPT_CLASSIFICAZIONE_RETAIL.splitlines()
        if "Da Classificare" in riga and re.search(
            r"(?:NON\s+e\s+MAI|non\s+e\s+mai|MAI\s+una\s+risposta|NON\s+e\s+una\s+risposta)",
            _normalizza(riga), re.IGNORECASE,
        )
    ]
    assert not divieti, (
        "Il prompt retail vieta all'AI la categoria che la regola di dominio #1 "
        f"impone di usare quando non riconosce la riga: {divieti}"
    )


def test_il_prompt_retail_ammette_esplicitamente_la_categoria_di_dominio():
    assert CATEGORIA_NON_CLASSIFICATA in PROMPT_CLASSIFICAZIONE_RETAIL


def test_il_prompt_retail_non_spinge_a_indovinare_quando_incerto():
    testo = PROMPT_CLASSIFICAZIONE_RETAIL.lower()
    assert "se non sei sicuro, scegli la categoria più probabile" not in testo
    assert "categoria più probabile" not in testo
    assert "categoria piu' probabile" not in testo


def test_il_divieto_su_note_e_diciture_resta_anche_nel_retail():
    """Regola di dominio #2: NOTE e' riservata all'admin, l'AI non la usa.

    Vale identica per un negozio: la categoria non e' in
    `categorie_ammesse('retail')`, quindi una NOTE proposta dall'AI verrebbe
    comunque scartata a valle — ma il prompt non deve nemmeno suggerirla.
    """
    assert "NOTE E DICITURE" in PROMPT_CLASSIFICAZIONE_RETAIL
    assert re.search(
        r'NON usare MAI "NOTE E DICITURE"', PROMPT_CLASSIFICAZIONE_RETAIL
    ), "Il divieto sulle NOTE all'AI e' corretto e non va rimosso"


def test_la_grafia_errata_non_compare_nel_prompt_retail():
    """'Da Clasificare' (una sola s) e' una variante sbagliata nota."""
    assert "Da Clasificare" not in PROMPT_CLASSIFICAZIONE_RETAIL


def test_get_prompt_classificazione_retail_sostituisce_gli_articoli():
    reso = get_prompt_classificazione("1. TRAPANO AVVITATORE", settore=SETTORE_RETAIL)
    assert "{ARTICOLI}" not in reso
    assert "TRAPANO AVVITATORE" in reso


# ── i vincoli che valgono solo per il retail ─────────────────────────────────

def test_il_prompt_retail_nomina_la_sua_unica_categoria_merce():
    assert CATEGORIA_ARTICOLO_DI_VENDITA in PROMPT_CLASSIFICAZIONE_RETAIL


@pytest.mark.parametrize("spesa", CATEGORIE_SPESE_GENERALI)
def test_il_prompt_retail_nomina_le_quattro_spese_generali(spesa):
    assert spesa in PROMPT_CLASSIFICAZIONE_RETAIL


def test_il_prompt_retail_non_offre_nessuna_categoria_food_come_uscita():
    """Nessuna food puo' essere PROPOSTA come categoria da usare.

    Si misurano le uscite, non le occorrenze di testo: il prompt nomina alcune
    food dentro un divieto esplicito ("NON usare MAI categorie alimentari
    (CARNE, PESCE, VINI...)"), che e' il contrario di offrirle.

    Una food e' "proposta" se compare in una riga numerata dell'elenco delle
    categorie ammesse o nell'elenco finale dei valori validi — gli unici due
    punti del prompt che dicono all'AI cosa PUO' rispondere. Il confronto e'
    per riga intera dell'elenco, non per sottostringa: "SHOP" (categoria food
    dei ristoranti) e' contenuta in "SHOPPER", che e' una parola comune.
    """
    ammesse_dal_prompt = []
    for riga in PROMPT_CLASSIFICAZIONE_RETAIL.splitlines():
        # le 5 voci dell'elenco: "1. **ARTICOLO DI VENDITA** - ..."
        voce = re.match(r"^\d+\. \*\*([^*]+)\*\* -", riga)
        if voce:
            ammesse_dal_prompt.append(voce.group(1).strip())
    assert len(ammesse_dal_prompt) == 5, (
        f"L'elenco delle categorie ammesse non ha 5 voci: {ammesse_dal_prompt}"
    )
    food_proposte = [c for c in ammesse_dal_prompt if c in CATEGORIE_FOOD_BEVERAGE]
    assert not food_proposte, (
        f"Il prompt retail propone categorie food: {food_proposte}"
    )

    blocco = PROMPT_CLASSIFICAZIONE_RETAIL.split("Usa esattamente uno di questi 6 valori")[-1]
    valide = set(re.findall(r'"([^"]+)"', blocco.split("\n\n")[0]))
    assert not (valide & set(CATEGORIE_FOOD_BEVERAGE)), (
        f"L'elenco finale dei valori validi contiene food: {valide & set(CATEGORIE_FOOD_BEVERAGE)}"
    )


def test_il_prompt_retail_vieta_esplicitamente_le_categorie_food():
    """Il divieto non e' decorativo: senza dizionario ne' safety net a valle,
    e' l'unica cosa che trattiene GPT dal proporre CARNE su una salumeria."""
    assert "NON usare MAI categorie alimentari" in PROMPT_CLASSIFICAZIONE_RETAIL


def test_il_prompt_retail_elenca_esattamente_le_uscite_ammesse():
    """Il blocco di formato deve enumerare le 6 uscite valide e nient'altro.

    Le uscite sono ARTICOLO DI VENDITA + le 4 spese generali + Da Classificare:
    la stessa partizione di `settore_service.categorie_ammesse('retail')` piu'
    la categoria di dominio. Se qualcuno aggiunge una sesta categoria merce al
    prompt senza aggiungerla alla whitelist, l'AI la proporrebbe e la
    validazione la scarterebbe: sintomo indistinguibile da "il prompt non
    funziona".
    """
    from services.settore_service import categorie_ammesse

    blocco = re.search(
        r'Usa esattamente uno di questi 6 valori.*?\n((?:.*\n)*?)\n',
        PROMPT_CLASSIFICAZIONE_RETAIL,
    )
    assert blocco, "Il prompt retail non elenca piu' le uscite ammesse"
    elencate = set(re.findall(r'"([^"]+)"', blocco.group(1)))
    attese = set(categorie_ammesse(SETTORE_RETAIL)) | {CATEGORIA_NON_CLASSIFICATA}
    assert elencate == attese, (
        f"Uscite elencate nel prompt: {sorted(elencate)}; "
        f"whitelist del settore + Da Classificare: {sorted(attese)}"
    )


def test_il_prompt_retail_non_parla_di_ristoranti():
    """Il testo e' per un negozio: "ristorante" nel prompt e' un residuo copiato."""
    testo = PROMPT_CLASSIFICAZIONE_RETAIL.lower()
    for parola in ("ristorante", "ristoranti", "cucina", "culinaria", "menu"):
        assert parola not in testo, f"'{parola}' non ha senso nel prompt di un negozio"


# ── il vincolo di Mattia: i ristoranti non cambiano di una virgola ───────────

@pytest.mark.parametrize("settore", [None, "ristorazione"])
def test_per_i_ristoranti_il_prompt_e_letteralmente_quello_di_oggi(settore):
    """Uguaglianza, non `in`: un solo carattere in piu' e' un cambiamento.

    E' il presidio del vincolo assoluto della Fase 2 — i clienti ristorazione
    non subiscono NESSUN cambiamento.
    """
    atteso = PROMPT_CLASSIFICAZIONE_AI.replace("{ARTICOLI}", '["MOZZARELLA"]')
    assert get_prompt_classificazione('["MOZZARELLA"]', settore=settore) == atteso


def test_un_settore_sconosciuto_ricade_sui_ristoranti():
    """Fail-safe nella direzione giusta, come `settore_service`."""
    atteso = PROMPT_CLASSIFICAZIONE_AI.replace("{ARTICOLI}", "X")
    assert get_prompt_classificazione("X", settore="qualcosa_di_ignoto") == atteso


def test_la_firma_resta_additiva():
    """Chi chiama con un solo argomento ottiene il comportamento di prima."""
    assert get_prompt_classificazione("X") == PROMPT_CLASSIFICAZIONE_AI.replace("{ARTICOLI}", "X")


def test_i_due_prompt_sono_testi_diversi():
    assert PROMPT_CLASSIFICAZIONE_RETAIL != PROMPT_CLASSIFICAZIONE_AI
    assert "{ARTICOLI}" in PROMPT_CLASSIFICAZIONE_RETAIL
