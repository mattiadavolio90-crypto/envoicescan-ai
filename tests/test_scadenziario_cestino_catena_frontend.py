"""In catena lo svuotamento del cestino nomina la sede che svuota.

Perche' esiste
==============
Il cestino di gruppo elenca le fatture di tutte le sedi e lo svuotamento agisce
su una sola (per scelta: tutte con un clic e' troppo pericoloso). Il bottone
diceva «Svuota questa sede» senza dire quale, il worker svuotava la sede di
sessione e il toast diceva «Cestino svuotato» anche con 0 righe eliminate
(audit di ottobre 2026, F4-11). Ora la conferma elenca le sedi per nome, il body
porta quella scelta e il toast legge `righe_eliminate`.
"""
import re
from pathlib import Path

from tests.helpers_ts import esegui_ts

MODULO = "lib/scadenziario"
RADICE = Path(__file__).resolve().parent.parent
CLIENT = RADICE / "apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx"
PROXY = RADICE / "apps/web/src/app/api/cestino/svuota/route.ts"


def test_sedi_nel_cestino_per_nome_con_il_conteggio():
    items = [
        {"file_origine": "a.xml", "ristorante_id": "r2", "sede_nome": "Varese"},
        {"file_origine": "b.xml", "ristorante_id": "r1", "sede_nome": "Como"},
        {"file_origine": "c.xml", "ristorante_id": "r2", "sede_nome": "Varese"},
        {"file_origine": "d.xml"},
    ]
    out = esegui_ts(MODULO, "emit(m.sediNelCestino(input));", items, richiede=["sediNelCestino"])
    assert out == [
        {"ristorante_id": "r1", "nome": "Como", "count": 1},
        {"ristorante_id": "r2", "nome": "Varese", "count": 2},
    ]


def _corpo(sorgente, firma):
    inizio = sorgente.index(firma)
    return sorgente[inizio:sorgente.index("\n  }\n", inizio) + 4]


def test_lo_svuotamento_manda_la_sede_e_legge_le_righe_eliminate():
    corpo = _corpo(CLIENT.read_text(encoding="utf-8"), "async function handleCestinoSvuota(")
    assert "body: JSON.stringify(sede ? { ristorante_id: sede.ristorante_id } : {})," in corpo
    assert "if (!data.righe_eliminate) toast.info(" in corpo
    assert "toast.success(sede ? `Cestino di ${sede.nome} svuotato` : \"Cestino svuotato\")" in corpo


def test_in_catena_la_conferma_elenca_le_sedi():
    s = CLIENT.read_text(encoding="utf-8")
    assert re.search(
        r"sediNelCestino\(cestinoItems\)\.map\(sede => \(.*?handleCestinoSvuota\(sede\)",
        s,
        re.S,
    )
    assert "Svuota questa sede" not in s
    assert "Elimini il cestino di questa sede?" not in s


def test_il_proxy_inoltra_il_body():
    s = PROXY.read_text(encoding="utf-8")
    assert "const body = await req.json().catch(() => ({}));" in s
    assert "body: JSON.stringify(body)," in s
