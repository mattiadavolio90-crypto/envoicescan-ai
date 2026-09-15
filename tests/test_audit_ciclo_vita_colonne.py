"""Il rilevatore del ciclo di vita delle colonne (lente L5) misura davvero.

Perche' questo presidio esiste
==============================
`scripts/audit_ciclo_vita_colonne.py` e' l'inventario riproducibile della
lente L5: dice quali colonne del DB nessuno nomina, quali sono lette e mai
scritte, quali scritte e mai lette. Un rilevatore che si rompe in silenzio e'
peggio di nessun rilevatore — ed e' successo il 15/09/2026, alla prima stesura:
10 file Python col BOM (fra cui `fastapi_worker.py`, 8.930 righe) non si
lasciavano parsare e venivano SALTATI senza dirlo, e due colonne vive risultavano
"scritte mai lette".

Qui il rilevatore gira su un mini-repo sintetico costruito in `tmp_path`, dove
ogni esito e' noto per costruzione. Ogni test copre una trappola pagata:
- il BOM (file saltato in silenzio);
- `ack` dentro "fallback" (word boundary);
- creazione != uso (ADD COLUMN e la riga di CREATE TABLE non sono un uso);
- il trigger che scrive `NEW.col` senza comparire nel codice;
- `.select(_COSTANTE)` con la stringa in una costante di modulo;
- i dati che smentiscono il rilevatore (colonna "mai scritta" nel codice ma
  piena a DB: la scrittura e' opaca, non assente).

L'ultimo test lancia la taratura sul repo VERO: se i casi noti non tornano piu'
(le due colonne morte di L4, le quattro vive), e' il rilevatore che va guardato.
"""
from __future__ import annotations

import csv
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.audit_ciclo_vita_colonne as modulo  # noqa: E402

SNAPSHOT = """\
CREATE TABLE IF NOT EXISTS public.turni (
    id bigint NOT NULL,
    ack boolean DEFAULT false,
    costo numeric,
    letta_sola text,
    piena_a_db text,
    sola_def text,
    dal_trigger text,
    da_costante text,
    scritta_e_basta text,
    created_at timestamp with time zone DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.altra (
    id bigint NOT NULL,
    costo numeric,
    scritta_e_letta text
);
CREATE OR REPLACE FUNCTION public.trg_turni() RETURNS trigger LANGUAGE plpgsql AS $function$
BEGIN
    NEW.dal_trigger := 'x';
    RETURN NEW;
END;
$function$;
CREATE TRIGGER trg_turni_biu BEFORE INSERT ON public.turni FOR EACH ROW EXECUTE FUNCTION trg_turni();
"""

MIGRAZIONE = """\
-- commento che nomina sola_def e letta_sola: i commenti non contano
ALTER TABLE public.turni ADD COLUMN sola_def text;
COMMENT ON COLUMN public.turni.sola_def IS 'letta_sola';
UPDATE public.turni SET scritta_e_basta = 'x' WHERE id = 1;
INSERT INTO public.altra (id, scritta_e_letta) VALUES (1, 'x');
SELECT scritta_e_letta FROM public.altra WHERE id = 1;
"""

PYTHON_CON_BOM = "﻿" + '''
_SELECT_TURNI = "id,da_costante"


def leggi(sb):
    r = sb.table("turni").select("id,costo,letta_sola,piena_a_db").eq("id", 1).execute()
    q = sb.table("turni").select(_SELECT_TURNI).execute()
    return r.data[0]["costo"], q


def scrivi(sb, payload):
    sb.table("turni").insert({"costo": 1}).execute()
    sb.table("altra").insert(payload).execute()   # opaca: la tabella non dice cosa scrive
    return "fallback"
'''

TYPESCRIPT = """\
const r = await sb.from("turni").update({ costo: 2, created_at: "x" }).eq("id", 1)
const s = await sb.from("turni").select("id,costo")
"""


@pytest.fixture
def repo(tmp_path, monkeypatch):
    (tmp_path / "supabase").mkdir()
    (tmp_path / "supabase" / "schema_snapshot.sql").write_text(SNAPSHOT, encoding="utf-8")
    (tmp_path / "supabase" / "migrations").mkdir()
    (tmp_path / "supabase" / "migrations" / "001.sql").write_text(MIGRAZIONE, encoding="utf-8")
    (tmp_path / "services").mkdir()
    (tmp_path / "services" / "mod.py").write_text(PYTHON_CON_BOM, encoding="utf-8")
    (tmp_path / "apps" / "web" / "src").mkdir(parents=True)
    (tmp_path / "apps" / "web" / "src" / "a.ts").write_text(TYPESCRIPT, encoding="utf-8")
    monkeypatch.setattr(modulo, "ROOT", tmp_path)
    return tmp_path


def _inventario(repo, stat=None):
    righe, meta = modulo.inventario(repo / "supabase" / "schema_snapshot.sql", stat)
    return righe, meta


def test_il_bom_non_fa_saltare_il_file(repo):
    """Il file Python inizia con U+FEFF: le sue letture vanno contate, e
    `non_parsati` deve restare vuoto. Prima del 15/09 fastapi_worker.py spariva."""
    righe, meta = _inventario(repo)
    assert meta["non_parsati"] == []
    assert righe["turni.letta_sola"]["letture_tab"] >= 1


def test_un_file_che_non_parsa_viene_dichiarato(repo):
    (repo / "services" / "rotto.py").write_text("def (:\n", encoding="utf-8")
    righe, meta = _inventario(repo)
    assert meta["non_parsati"] == ["services/rotto.py"]
    assert any("rotto.py" in e for e in modulo.taratura(righe, meta))


def test_ack_non_matcha_dentro_fallback(repo):
    righe, _ = _inventario(repo)
    assert righe["turni.ack"]["file_codice"] == 0
    assert righe["turni.ack"]["esito"] == "mai_nominata"


def test_creazione_non_e_uso(repo):
    """ADD COLUMN, COMMENT ON e il commento `--` nominano sola_def: non e' un uso."""
    righe, _ = _inventario(repo)
    assert righe["turni.sola_def"]["file_sql_uso"] == 0
    assert righe["turni.sola_def"]["esito"] == "mai_nominata"


def test_update_sql_e_una_scrittura_attribuita(repo):
    righe, _ = _inventario(repo)
    r = righe["turni.scritta_e_basta"]
    assert r["scritture_tab"] == 1
    assert r["esito"] == "scritta_mai_letta"


def test_scritta_e_letta_nello_stesso_file_sql_ha_entrambe(repo):
    """INSERT e SELECT nello stesso file: la lettura non sparisce perche' c'e'
    la scrittura. Alla prima stesura spariva (rilievo del code-reviewer, 15/09)."""
    righe, _ = _inventario(repo)
    r = righe["altra.scritta_e_letta"]
    assert r["scritture_tab"] == 1
    assert r["letture_nome"] == 1
    assert r["esito"] == "viva"


def test_il_trigger_scrive_senza_comparire_nel_codice(repo):
    righe, _ = _inventario(repo)
    r = righe["turni.dal_trigger"]
    assert r["file_codice"] == 0
    assert r["scritture_tab"] == 1, "NEW.dal_trigger := ... nel trigger ON turni"


def test_select_con_costante_di_modulo(repo):
    righe, _ = _inventario(repo)
    assert righe["turni.da_costante"]["letture_tab"] == 1


def test_insert_dizionario_e_attribuito_e_insert_variabile_e_opaco(repo):
    righe, _ = _inventario(repo)
    assert righe["turni.costo"]["scritture_tab"] >= 2, "insert Python + update TypeScript"
    assert righe["turni.costo"]["esito"] == "viva"
    assert righe["altra.costo"]["scritture_opache"] == 1
    assert righe["altra.costo"]["scritture_tab"] == 0


def test_letta_mai_scritta_senza_dati(repo):
    righe, _ = _inventario(repo)
    assert righe["turni.letta_sola"]["esito"] == "letta_mai_scritta"


def test_i_dati_smentiscono_il_rilevatore(repo, tmp_path):
    """piena_a_db e' letta e il codice non la scrive mai in modo visibile: se a DB
    e' piena, la scrittura c'e' (opaca) e l'esito e' viva. Se e' NULL al 100%
    resta letta_mai_scritta: e' la firma della classe grave."""
    csv_path = tmp_path / "stat.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tabella", "colonna", "tipo", "nullable", "default", "n", "nn", "nd"])
        w.writerow(["turni", "piena_a_db", "text", "YES", "", 10, 10, 3])
        w.writerow(["turni", "letta_sola", "text", "YES", "", 10, 0, 0])
    stat = modulo.leggi_stat(csv_path)
    righe, _ = _inventario(repo, stat)
    assert righe["turni.piena_a_db"]["esito"] == "viva"
    assert righe["turni.letta_sola"]["esito"] == "letta_mai_scritta"
    assert righe["turni.letta_sola"]["dati"] == "NULL_100"


def test_il_drift_dello_snapshot_viene_dichiarato(repo, tmp_path):
    csv_path = tmp_path / "stat.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tabella", "colonna", "tipo", "nullable", "default", "n", "nn", "nd"])
        w.writerow(["turni", "nuova", "text", "YES", "", 10, 0, 0])
    righe, meta = _inventario(repo, modulo.leggi_stat(csv_path))
    assert meta["drift_snapshot"] == ["turni.nuova"]
    assert "turni.nuova" in righe


def test_taratura_sul_repo_vero():
    """I casi di esito noto (L4: due colonne morte; quattro vive) devono tornare
    sullo snapshot e sul codice VERI. Se fallisce, e' cambiato il rilevatore o
    il repo, e l'inventario non va creduto finche' non si capisce quale."""
    stat = modulo.leggi_stat(ROOT / "docs" / "storico" / "audit-2026-09" / "L5_stat_colonne_2026-09-15.csv")
    righe, meta = modulo.inventario(modulo.SNAPSHOT, stat)
    assert modulo.taratura(righe, meta) == []
    assert meta["non_parsati"] == []
