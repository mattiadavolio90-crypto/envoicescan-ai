"""Il radar anomalie deve essere invocato dal percorso vivo.

Il difetto storico non era solo la query rotta: l'unico call site stava in
`upload_handler.handle_uploaded_files`, raggiungibile solo da `legacy_streamlit/`,
che nessun modulo vivo importa. Nessun test verificava che il radar fosse
davvero collegato a qualcosa, quindi il fatto che non girasse da sempre non
faceva fallire niente.

Questi test guardano il sorgente di `salva_fattura_processata` — l'unico collo
di bottiglia condiviso dai due canali vivi (upload manuale e SDI).
"""

import inspect
import re

import services.invoice_service as invoice_service


def _sorgente_salva():
    return inspect.getsource(invoice_service.salva_fattura_processata)


def test_salva_fattura_processata_invoca_il_radar():
    src = _sorgente_salva()
    assert 'check_on_upload' in src, (
        'Il radar non e\' agganciato al percorso vivo: se sparisce di qui, '
        'torna a non girare per nessuno dei due canali.'
    )


def test_il_radar_riceve_il_correlatore_giusto():
    """Deve passare `file_origini`, non un id di upload sintetico."""
    src = _sorgente_salva()
    blocco = src[src.index('check_on_upload'):]
    assert 'file_origini' in blocco[:400]
    assert 'upload_id' not in blocco[:400]


def test_le_notifiche_del_radar_vengono_scritte():
    src = _sorgente_salva()
    assert 'upsert_inbox_notifications' in src, (
        'Senza upsert il radar calcola le anomalie e le butta via.'
    )


def test_il_fallimento_del_radar_non_blocca_il_salvataggio():
    """Best-effort: una fattura non deve andare persa perche' il radar cade."""
    src = _sorgente_salva()
    i = src.index('check_on_upload')
    prima = src[:i]
    assert prima.rstrip().endswith('(') or 'try:' in prima[-500:], (
        'La chiamata al radar deve stare dentro un try/except.'
    )
    dopo = src[i:i + 1200]
    assert 'except Exception' in dopo


def test_l_errore_del_radar_e_loggato_con_dettaglio():
    """Il vecchio call site silenziava l'eccezione: e' cosi' che il bug e'
    rimasto invisibile. L'errore va loggato, con lo stack."""
    src = _sorgente_salva()
    dopo = src[src.index('check_on_upload'):]
    blocco = dopo[:1400]
    assert 'logger.warning' in blocco
    assert 'exc_info=True' in blocco, (
        'Serve lo stack trace: un warning senza dettaglio non fa notare '
        'una query rotta.'
    )


# ── Test comportamentali ─────────────────────────────────────────────────
# I test sopra leggono il sorgente: blindano che l'aggancio non venga
# cancellato, ma NON eseguono nulla. Il code-reviewer ha mostrato il loro
# limite trovando un call site rimasto con la firma vecchia
# (`upload_handler.py`, kwarg `upload_id`): un mismatch di firma passa
# indisturbato un assert su stringhe. Questi invece chiamano davvero.

import inspect

import pytest

from services.anomaly_radar_service import check_on_upload


def test_ogni_chiamante_e_compatibile_con_la_firma():
    """Nessun call site deve poter sollevare TypeError.

    E' il difetto che l'except Exception del radar inghiottirebbe in
    silenzio — lo stesso meccanismo che ha tenuto invisibile per mesi la
    query sulla colonna inesistente.
    """
    firma = inspect.signature(check_on_upload)
    # la forma usata dall'unico chiamante vivo (invoice_service)
    firma.bind(
        user_id='u1',
        ristorante_id='r1',
        file_origini=['a.xml'],
        supabase_client=None,
    )


def test_la_vecchia_firma_non_e_piu_accettata():
    """Se qualcuno reintroduce `upload_id=`, deve rompersi subito e forte."""
    firma = inspect.signature(check_on_upload)
    with pytest.raises(TypeError):
        firma.bind(
            user_id='u1', ristorante_id='r1',
            upload_id='20260829120000', supabase_client=None,
        )


def test_ogni_call_site_del_repo_rispetta_la_firma():
    """Analizza l'AST di tutto il codice di produzione, non il testo.

    Un grep riga-per-riga NON basta: nel call site reale il kwarg sbagliato
    stava su una riga diversa da `check_on_upload(`. Provato — il grep
    passava. Qui si estrae ogni chiamata e le si applica `signature.bind`,
    che e' esattamente il controllo che conta.
    """
    import ast
    from pathlib import Path as _Path

    firma = inspect.signature(check_on_upload)
    radice = _Path('/workspaces/ONEFLUX')
    problemi = []

    for cartella in ('services', 'worker', 'utils', 'config'):
        for file_py in (radice / cartella).rglob('*.py'):
            try:
                albero = ast.parse(file_py.read_text(encoding='utf-8-sig'))
            except SyntaxError:
                continue
            for nodo in ast.walk(albero):
                if not isinstance(nodo, ast.Call):
                    continue
                nome = getattr(nodo.func, 'id', None) or getattr(nodo.func, 'attr', None)
                if nome != 'check_on_upload':
                    continue
                kwargs = {k.arg: None for k in nodo.keywords if k.arg}
                posizionali = [None] * len(nodo.args)
                try:
                    firma.bind(*posizionali, **kwargs)
                except TypeError as exc:
                    problemi.append(
                        f'{file_py.relative_to(radice)}:{nodo.lineno} -> {exc}'
                    )

    assert not problemi, (
        'Call site incompatibili con la firma di check_on_upload:\n'
        + '\n'.join(problemi)
    )



# ============================================================
# check_weekly: catena morta a due anelli (misurato 31/08/2026)
# ============================================================
#
# `check_weekly` non ha chiamanti. La roadmap lo dava come "residuo da
# rimuovere", ma la misura dice altro: agganciarlo non produrrebbe NULLA, perche'
# legge un topic che nessun percorso vivo SCRIVE piu' su notification_inbox.
#
# Questi test fissano i due anelli. Se un domani qualcuno rende `price_alert`
# scrivibile dal percorso vivo, il secondo test fallisce: e' il segnale che
# `check_weekly` e' tornato agganciabile e la decisione va ripresa.
#
# TECNICA: AST, non match testuale. La prima stesura cercava la stringa
# `topic_key='price_alert'` riga per riga e sbagliava in ENTRAMBI i sensi:
#   - falso positivo sul docstring che documenta il difetto (una menzione non e'
#     un emettitore);
#   - falso NEGATIVO su `fastapi_worker.py:6443`, dove il topic e' una chiave di
#     dict (`"topic_key": "price_alert"`) e non un kwarg. Il `code-reviewer` l'ha
#     trovato provandolo per mutazione: montando la forma dict, il test restava
#     verde.
# Un match testuale misura il proprio pattern, non il codice: qui si guarda
# l'albero, che vede le due forme e ignora commenti e stringhe di documentazione.

import ast

_RUNTIME = ('services', 'utils', 'config', 'worker')


def _alberi_runtime():
    """(path_relativo, AST) per ogni .py del runtime vivo.

    `legacy_streamlit/` e' escluso per definizione: e' il percorso morto.
    """
    import pathlib

    radice = pathlib.Path(__file__).resolve().parent.parent
    for pkg in _RUNTIME:
        for py in sorted((radice / pkg).rglob('*.py')):
            try:
                albero = ast.parse(py.read_text(encoding='utf-8-sig', errors='ignore'))
            except SyntaxError:
                continue
            yield str(py.relative_to(radice)), albero


def test_check_weekly_non_ha_ancora_chiamanti():
    """Se qualcuno lo aggancia, deve accorgersi del test sotto."""
    chiamanti = []
    for rel, albero in _alberi_runtime():
        for nodo in ast.walk(albero):
            if isinstance(nodo, ast.Call):
                nome = getattr(nodo.func, 'id', None) or getattr(nodo.func, 'attr', None)
                if nome == 'check_weekly':
                    chiamanti.append(f'{rel}:{nodo.lineno}')

    assert chiamanti == [], (
        'check_weekly ora ha chiamanti: ' + ', '.join(chiamanti) + '.\n'
        "Non e' un errore di per se', ma va verificato che a monte esista un "
        "SCRITTORE vivo di topic_key='price_alert' su notification_inbox: senza "
        'quello legge 0 righe e torna [] per sempre. Vedi il docstring di '
        'anomaly_radar_service.'
    )


def _sorgenti_price_alert():
    """(file, riga) dove 'price_alert' e' associato a un topic_key, in ogni forma.

    Copre il kwarg `topic_key='price_alert'` e la chiave di dict
    `{"topic_key": "price_alert"}`. Le stringhe di documentazione non sono
    chiamate ne' dict, quindi non compaiono: e' il vantaggio dell'AST.
    """
    trovati = []
    for rel, albero in _alberi_runtime():
        for nodo in ast.walk(albero):
            if isinstance(nodo, ast.Call):
                for kw in nodo.keywords:
                    if (kw.arg == 'topic_key'
                            and isinstance(kw.value, ast.Constant)
                            and kw.value.value == 'price_alert'):
                        trovati.append((rel, nodo.lineno))
            elif isinstance(nodo, ast.Dict):
                for chiave, valore in zip(nodo.keys, nodo.values):
                    if (isinstance(chiave, ast.Constant) and chiave.value == 'topic_key'
                            and isinstance(valore, ast.Constant)
                            and valore.value == 'price_alert'):
                        trovati.append((rel, chiave.lineno))
    return trovati


def test_price_alert_non_ha_scrittori_vivi_su_notification_inbox():
    """L'anello che manca davvero.

    `check_weekly` legge da `notification_inbox` le righe con
    `topic_key='price_alert'`. Perche' ne esistano, qualcuno deve PERSISTERLE
    con `build_notification_record` + `upsert_inbox_notifications`.

    Sorgenti noti al 31/08/2026, entrambi innocui:
      - `upload_handler.py` — persiste davvero, ma sta in `handle_uploaded_files`,
        cioe' il percorso `legacy_streamlit` gia' dichiarato morto dagli altri
        test di questo file. Ultima riga sul DB: 1/6/2026.
      - `fastapi_worker.py` — `_briefing_raccogli_notifiche` costruisce un dict
        in memoria con `source_type='live'` per il briefing: non tocca
        `notification_inbox`.

    Quando questo test fallisce la notizia e' buona: qualcuno ha aggiunto un
    sorgente nuovo, e va deciso se PERSISTE (allora `check_weekly` torna ad
    avere senso) o se e' un'altra vista in memoria (allora si aggiunge qui).
    """
    noti = {'services/upload_handler.py', 'services/fastapi_worker.py'}
    trovati = _sorgenti_price_alert()

    nuovi = [f'{rel}:{n}' for rel, n in trovati if rel not in noti]
    assert nuovi == [], (
        'Nuovo sorgente di price_alert fuori da quelli noti: ' + ', '.join(nuovi) + '.\n'
        "Verifica se PERSISTE su notification_inbox (upsert_inbox_notifications) "
        "o se e' solo una vista in memoria. Se persiste dal percorso vivo, "
        '`check_weekly` puo\' tornare a produrre notifiche: vedi il docstring di '
        'anomaly_radar_service.'
    )

    assert trovati, (
        "Nessun sorgente di price_alert nel runtime: se sono stati rimossi, va "
        "rimosso anche `check_weekly`, perche' non puo' piu' leggere nulla."
    )
