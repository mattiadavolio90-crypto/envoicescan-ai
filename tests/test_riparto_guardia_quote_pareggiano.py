"""La guardia SQL che rifiuta quote non pareggianti (migration 20260828210000).

`tests/test_riparto_quote.py` difende l'invariante negli helper Python. Ma tutti
e 19 gli sbilanciamenti trovati sul DB live nell'audit 2026-08 (F-DRIFT) erano
stati scritti da un percorso che quegli helper non li usava, e nessun test se ne
era accorto: l'invariante era difeso dal *chiamante*, non dal *confine*.

Da qui la guardia dentro le due RPC — `crea_riparto_con_quote` e
`sostituisci_quote_riparto` — che sono l'unico passaggio obbligato di ogni
scrittura di quote. Questi test verificano che la migration contenga davvero il
controllo su entrambe, perché una guardia messa su una sola delle due lascerebbe
aperto proprio il percorso da cui il drift proveniva (tutti e 19 su costi
ri-scritti, zero su costi appena creati).

Il perché conta: `riparto_quote_mensili` somma le quote dentro `margini_mensili`,
quindi uno scarto sulle quote non resta nella sua tabella — entra nel MOL che il
cliente legge.
"""
import re
from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "supabase/migrations/20260828210000_riparto_quote_pareggiano_header.sql"
)

RPC_CHE_SCRIVONO_QUOTE = ["crea_riparto_con_quote", "sostituisci_quote_riparto"]


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION.exists(), (
        "la migration della guardia F-DRIFT non esiste più: se è stata rinominata "
        "aggiorna questo test, non cancellarlo"
    )
    return MIGRATION.read_text(encoding="utf-8")


def _corpo_funzione(sql: str, nome: str) -> str:
    """Isola il corpo di una funzione: la guardia va verificata DENTRO la
    funzione giusta, non da qualche parte nel file."""
    m = re.search(
        rf"CREATE OR REPLACE FUNCTION public\.{nome}\(.*?\n\$\$;",
        sql,
        re.S,
    )
    assert m, f"{nome} non ridefinita nella migration"
    return m.group(0)


@pytest.mark.parametrize("rpc", RPC_CHE_SCRIVONO_QUOTE)
def test_ogni_rpc_che_scrive_quote_ha_la_guardia(sql, rpc):
    corpo = _corpo_funzione(sql, rpc)
    assert "RAISE EXCEPTION" in corpo and "non pareggiano" in corpo, (
        f"{rpc} scrive quote senza verificare che pareggino l'importo del costo"
    )


@pytest.mark.parametrize("rpc", RPC_CHE_SCRIVONO_QUOTE)
def test_la_guardia_somma_le_quote_ricevute(sql, rpc):
    """Deve sommare `quota_importo` dal JSON in ingresso, non fidarsi di un
    totale passato dal chiamante: sarebbe il chiamante a garantire l'invariante,
    cioè esattamente ciò che non ha funzionato."""
    corpo = _corpo_funzione(sql, rpc)
    assert "jsonb_array_elements(p_quote)" in corpo
    assert re.search(r"SUM\(\(q->>'quota_importo'\)::NUMERIC\)", corpo), (
        f"{rpc}: la guardia non somma le quote effettivamente ricevute"
    )


@pytest.mark.parametrize("rpc", RPC_CHE_SCRIVONO_QUOTE)
def test_la_guardia_precede_la_scrittura(sql, rpc):
    """Ordine: se il controllo stesse dopo l'INSERT, la transazione verrebbe sì
    annullata, ma il vincolo diventerebbe un dettaglio di implementazione di
    Postgres invece di una decisione esplicita."""
    corpo = _corpo_funzione(sql, rpc)
    pos_guardia = corpo.index("non pareggiano")
    pos_insert = corpo.index("INSERT INTO public.riparto_costi_catena_quote")
    assert pos_guardia < pos_insert, f"{rpc}: la guardia scatta dopo la scrittura"


@pytest.mark.parametrize("rpc", RPC_CHE_SCRIVONO_QUOTE)
def test_tolleranza_di_un_centesimo_non_di_piu(sql, rpc):
    """La tolleranza esiste per i residui di rappresentazione, non per coprire
    sbilanciamenti veri. Un valore più largo (0.1, 1) renderebbe la guardia
    inutile proprio sulla classe di errori che deve intercettare: gli scarti
    reali trovati erano di 1 centesimo."""
    corpo = _corpo_funzione(sql, rpc)
    m = re.search(r"abs\(v_somma - round\(p_importo_totale, 2\)\) > ([0-9.]+)", corpo)
    assert m, f"{rpc}: confronto della tolleranza non riconosciuto"
    assert float(m.group(1)) == 0.01, (
        f"{rpc}: tolleranza {m.group(1)} invece di 0.01 — a 0.1 i 19 drift reali "
        "sarebbero passati tutti"
    )


def test_sanatoria_sposta_un_solo_centesimo_per_costo(sql):
    """La sanatoria degli storici deve correggere UNA riga per costo (DISTINCT ON),
    non spalmare lo scarto su tutte: spalmare cambierebbe quote che erano giuste."""
    assert "DISTINCT ON (s.riparto_id)" in sql, (
        "senza DISTINCT ON la sanatoria toccherebbe più righe per costo"
    )
    assert "HAVING round(SUM(q.quota_importo), 2) <> c.importo_totale" in sql, (
        "la sanatoria deve selezionare solo i costi davvero sbilanciati"
    )


def test_sanatoria_non_puo_creare_quote_negative(sql):
    """`quota_importo` ha un CHECK >= 0: una sanatoria che lo violasse farebbe
    fallire la migration a metà applicazione."""
    assert "d.nuovo_importo >= 0" in sql, (
        "la sanatoria non si protegge dal CHECK quota_importo >= 0"
    )


def test_le_due_rpc_restano_transazionali(sql):
    """La guardia non deve aver perso per strada la proprietà per cui le RPC
    esistono: padre e quote scritti insieme o per niente (incidente FASTWEB 22/7)."""
    for rpc in RPC_CHE_SCRIVONO_QUOTE:
        corpo = _corpo_funzione(sql, rpc)
        assert "LANGUAGE plpgsql" in corpo
        assert "SECURITY DEFINER" in corpo
        assert "SET search_path = public" in corpo, (
            f"{rpc}: search_path non fissato, SECURITY DEFINER diventa un rischio"
        )
