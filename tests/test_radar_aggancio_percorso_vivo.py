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
