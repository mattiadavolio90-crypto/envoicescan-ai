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
# legge un topic che nessun percorso vivo emette piu'.
#
# Questi test fissano i due anelli. Se un domani qualcuno rende `price_alert`
# emettibile dal percorso vivo, il secondo test fallisce: e' il segnale che
# `check_weekly` e' tornato agganciabile e la decisione va ripresa. Senza questo
# il fatto resterebbe scritto solo in un docstring, e un docstring non si accorge
# di essere diventato falso.
#
# Perimetro: i 4 package del runtime Python (gli stessi di CLAUDE.md).
# `legacy_streamlit/` e' escluso per definizione: e' il percorso morto.

_RUNTIME = ('services', 'utils', 'config', 'worker')


def _righe_runtime():
    """(path_relativo, n_riga, testo) per ogni .py del runtime vivo.

    Salta commenti, docstring e stringhe: una MENZIONE di `price_alert` dentro
    un docstring che spiega perche' il topic e' morto non e' un emettitore.
    Prima stesura di questo test: falliva sul docstring di
    `anomaly_radar_service` — cioe' sul testo che documenta il difetto. Un
    match testuale nudo misura il proprio pattern, non il codice.
    """
    import io as _io
    import pathlib
    import tokenize

    radice = pathlib.Path(__file__).resolve().parent.parent
    for pkg in _RUNTIME:
        for py in sorted((radice / pkg).rglob('*.py')):
            rel = str(py.relative_to(radice))
            testo = py.read_text(encoding='utf-8', errors='ignore')
            righe = testo.splitlines()
            # righe occupate da commenti o da stringhe multi-riga (docstring)
            escluse = set()
            try:
                for tok in tokenize.generate_tokens(_io.StringIO(testo).readline):
                    if tok.type == tokenize.COMMENT:
                        escluse.add(tok.start[0])
                    elif tok.type == tokenize.STRING and tok.end[0] > tok.start[0]:
                        escluse.update(range(tok.start[0], tok.end[0] + 1))
            except (tokenize.TokenError, IndentationError, SyntaxError):
                pass
            for n, riga in enumerate(righe, 1):
                if n not in escluse:
                    yield rel, n, riga


def test_check_weekly_non_ha_ancora_chiamanti():
    """Se qualcuno lo aggancia, deve accorgersi del test sotto."""
    chiamanti = [
        f'{rel}:{n}'
        for rel, n, riga in _righe_runtime()
        if 'check_weekly(' in riga and not riga.lstrip().startswith(('#', 'def '))
    ]
    assert chiamanti == [], (
        'check_weekly ora ha chiamanti: ' + ', '.join(chiamanti) + '.\n'
        "Non e' un errore di per se', ma va verificato che a monte esista un "
        "emettitore vivo di topic_key='price_alert': senza quello legge 0 righe "
        'e torna [] per sempre. Vedi il docstring di anomaly_radar_service.'
    )


def test_price_alert_non_ha_emettitori_vivi():
    """L'anello che manca davvero.

    `check_weekly` legge `topic_key='price_alert'`. L'unico emettitore sta in
    `upload_handler.handle_uploaded_files`, cioe' il percorso legacy_streamlit
    gia' dichiarato morto dagli altri test di questo file.

    Quando questo test fallisce, la notizia e' buona: qualcuno ha aggiunto un
    emettitore vivo e `check_weekly` torna ad avere senso.
    """
    emettitori = [
        (rel, n)
        for rel, n, riga in _righe_runtime()
        if "topic_key='price_alert'" in riga or 'topic_key="price_alert"' in riga
    ]

    vivi = [f'{rel}:{n}' for rel, n in emettitori if rel != 'services/upload_handler.py']
    assert vivi == [], (
        'Esiste un emettitore di price_alert fuori da upload_handler: '
        + ', '.join(vivi) + '.\n'
        "Se e' raggiungibile dal percorso vivo, `check_weekly` puo' tornare a "
        'produrre notifiche: va deciso se agganciarlo (vedi il docstring di '
        'anomaly_radar_service).'
    )

    assert emettitori, (
        "Nessun emettitore di price_alert nel runtime: se e' stato rimosso, va "
        "rimosso anche `check_weekly`, perche' non puo' piu' leggere nulla."
    )
