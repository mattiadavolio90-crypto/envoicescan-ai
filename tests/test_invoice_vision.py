"""`estrai_dati_da_scontrino_vision` — canale PDF/foto via OpenAI Vision.

⚠️ PERIMETRO: questo canale e' OGGI INATTIVO in produzione.
Misurato sul DB live il 10/8/2026, tre fonti indipendenti concordi:
  - 0 righe attive in `fatture` con estensione pdf/jpg/png (31.298 XML + 2.702 P7M)
  - 0 documenti con quelle estensioni **anche nel cestino**
  - 0 eventi in `ai_usage_events` con operation_type in ('pdf','vision'),
    su 443 eventi totali (max(created_at) NULL)
E l'unico call site — `services/upload_handler.py:1400` — sta dentro
`handle_uploaded_files` (893-2231), cioe' il blocco che l'audit §2 ha misurato
raggiungibile solo da `legacy_streamlit/app_controllers.py`.

La copertura qui e' quindi **prospettica, non protettiva**: nessun cliente puo'
rompere questo codice perche' nessun cliente lo esegue. E' stata scritta per
scelta esplicita, cosi' che se il canale PDF/foto verra' riattivato la rete
esista gia'. Di conseguenza il salto di coverage che questo file produce sul
modulo NON va letto come sicurezza aggiunta sui dati correnti.

Mutazioni verificate rosse: M25 (cap 20MB), M26 (quota), M27 (guardrail NOTE
del ramo Vision), M28 (JSON troncato).
"""
import io
import json
from unittest.mock import MagicMock, patch

import pytest


# ─── fake OpenAI (il client e' gia' un parametro: nessun patch del modulo) ─────

def _risposta(contenuto, prompt_tokens=1000, completion_tokens=500):
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=contenuto))]
    resp.usage = MagicMock(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    return resp


class _FakeOpenAI:
    def __init__(self, contenuto, usage=True):
        self._resp = _risposta(contenuto)
        if not usage:
            self._resp.usage = None
        self.chat = MagicMock()
        self.chat.completions.create.return_value = self._resp
        self.chiamate = self.chat.completions.create


PAYLOAD_OK = {
    "fornitore": "METRO SRL",
    "piva_cessionario": "01234567890",
    "data": "2026-03-15",
    "tipo_documento": "fattura",
    "righe": [
        {"descrizione": "mozzarella fiordilatte", "quantita": 2.0,
         "prezzo_unitario": 5.0, "totale": 10.0, "iva": 10},
    ],
}


def _file(nome="scontrino.pdf", size=1024):
    f = io.BytesIO(b"%PDF-1.4 finto contenuto")
    f.name = nome
    f.size = size
    return f


@pytest.fixture
def vision():
    """Esegue la funzione con session_state, categorizzazione e base64 mockati.

    `ottieni_categoria_prodotto` / `carica_memoria_completa` /
    `_applica_guardrail_note_con_importo` sono import LOCALI dentro la funzione:
    vanno patchati sul modulo sorgente `services.ai_service`.
    """
    from services.invoice_service import estrai_dati_da_scontrino_vision

    def _call(client, file_caricato=None, categoria='🧀 LATTICINI E FORMAGGI',
              session=None, track=None, quota=None):
        sess = {'user_data': {'id': 'user-1'}, 'ristorante_id': 'rist-1'}
        sess.update(session or {})

        mock_st = MagicMock()
        mock_st.session_state.get = lambda k, d=None: sess.get(k, d)

        ctx = [
            patch('services.invoice_service.st', mock_st),
            patch('services.invoice_service.converti_in_base64', return_value='ZmFrZQ=='),
            patch('services.ai_service.carica_memoria_completa', return_value=None),
            patch('services.ai_service.ottieni_categoria_prodotto', return_value=categoria),
            patch('services.ai_service.enforce_no_unclassified_category',
                  side_effect=lambda cat, desc, source=None: (cat, False)),
            patch('services.ai_cost_service.track_ai_usage', track or MagicMock()),
        ]
        if quota is not None:
            ctx.append(patch('services.ai_cost_service.get_daily_quota_status', quota))

        from contextlib import ExitStack
        with ExitStack() as stack:
            for c in ctx:
                stack.enter_context(c)
            return estrai_dati_da_scontrino_vision(file_caricato or _file(), client)

    return _call


class TestEstrazioneBase:

    def test_riga_estratta_dai_campi_del_json(self, vision):
        righe = vision(_FakeOpenAI(json.dumps(PAYLOAD_OK)))
        assert len(righe) == 1
        r = righe[0]
        assert r['Descrizione'] == 'MOZZARELLA FIORDILATTE'
        assert r['Quantita'] == 2.0
        assert r['Prezzo_Unitario'] == 5.0
        assert r['Totale_Riga'] == 10.0
        assert r['Fornitore'] == 'METRO SRL'
        assert r['Tipo_Documento'] == 'TD01'
        assert r['piva_cessionario'] == '01234567890'

    def test_iva_estratta_non_azzerata(self, vision):
        """L'IVA per riga alimenta lo scorporo e il guardrail IVA-bassa a valle:
        era hardcoded a 0 prima del fix, e questo test lo impedisce di nuovo."""
        righe = vision(_FakeOpenAI(json.dumps(PAYLOAD_OK)))
        assert righe[0]['IVA_Percentuale'] == 10

    def test_markdown_code_fence_rimosso(self, vision):
        testo = "```json\n" + json.dumps(PAYLOAD_OK) + "\n```"
        righe = vision(_FakeOpenAI(testo))
        assert len(righe) == 1

    def test_prezzo_unitario_calcolato_da_totale(self, vision):
        payload = json.loads(json.dumps(PAYLOAD_OK))
        payload['righe'][0].update({'prezzo_unitario': 0, 'totale': 30.0, 'quantita': 3.0})
        righe = vision(_FakeOpenAI(json.dumps(payload)))
        assert righe[0]['Prezzo_Unitario'] == 10.0

    def test_totale_calcolato_da_prezzo(self, vision):
        payload = json.loads(json.dumps(PAYLOAD_OK))
        payload['righe'][0].update({'totale': 0, 'prezzo_unitario': 4.0, 'quantita': 3.0})
        righe = vision(_FakeOpenAI(json.dumps(payload)))
        assert righe[0]['Totale_Riga'] == 12.0

    def test_valori_non_numerici_degradano_ai_default(self, vision):
        payload = json.loads(json.dumps(PAYLOAD_OK))
        payload['righe'][0].update({'quantita': 'due', 'prezzo_unitario': 'n/d', 'totale': 'x'})
        righe = vision(_FakeOpenAI(json.dumps(payload)))
        assert righe[0]['Quantita'] == 1.0
        assert righe[0]['Totale_Riga'] == 0

    def test_data_non_valida_sostituita_con_oggi(self, vision):
        payload = json.loads(json.dumps(PAYLOAD_OK))
        payload['data'] = 'non-una-data'
        righe = vision(_FakeOpenAI(json.dumps(payload)))
        assert righe[0]['Data_Documento'] != 'non-una-data'

    def test_nome_file_sanitizzato(self, vision):
        righe = vision(_FakeOpenAI(json.dumps(PAYLOAD_OK)),
                       file_caricato=_file(nome='../../etc/passwd'))
        assert righe[0]['File_Origine'] == 'etcpasswd'

    def test_unita_misura_normalizzata(self, vision):
        payload = json.loads(json.dumps(PAYLOAD_OK))
        payload['righe'][0]['unita_misura'] = 'kilogrammi'
        righe = vision(_FakeOpenAI(json.dumps(payload)))
        assert righe[0]['Unita_Misura'] == 'KG'


class TestNotaDiCredito:
    """Una NC caricata come PDF deve RIDURRE i costi, non aumentarli."""

    def _nc(self, righe):
        p = json.loads(json.dumps(PAYLOAD_OK))
        p['tipo_documento'] = 'nota_credito'
        p['righe'] = righe
        return json.dumps(p)

    def test_tutte_positive_invertite_in_blocco(self, vision):
        righe = vision(_FakeOpenAI(self._nc([
            {"descrizione": "reso mozzarella", "quantita": 1, "prezzo_unitario": 10.0,
             "totale": 10.0, "iva": 10},
        ])))
        assert righe[0]['Totale_Riga'] == -10.0
        assert righe[0]['Tipo_Documento'] == 'TD04'

    def test_con_righe_gia_negative_i_segni_sono_rispettati(self, vision):
        """`_tot_grezzo` rileva le righe negative: se il documento ha gia' i
        segni giusti, invertire in blocco li ribalterebbe di nuovo."""
        righe = vision(_FakeOpenAI(self._nc([
            {"descrizione": "reso a", "quantita": 1, "prezzo_unitario": -5.0,
             "totale": -5.0, "iva": 10},
            {"descrizione": "reso b", "quantita": 1, "prezzo_unitario": 3.0,
             "totale": 3.0, "iva": 10},
        ])))
        assert [r['Totale_Riga'] for r in righe] == [-5.0, 3.0]

    def test_totale_non_numerico_non_rompe_il_rilevamento(self, vision):
        righe = vision(_FakeOpenAI(self._nc([
            {"descrizione": "reso", "quantita": 1, "prezzo_unitario": 10.0,
             "totale": "n/d", "iva": 10},
        ])))
        assert righe[0]['Tipo_Documento'] == 'TD04'

    @pytest.mark.parametrize('marcatore', ['nota_credito', 'TD04', 'reso', 'storno'])
    def test_marcatori_riconosciuti(self, vision, marcatore):
        p = json.loads(json.dumps(PAYLOAD_OK))
        p['tipo_documento'] = marcatore
        righe = vision(_FakeOpenAI(json.dumps(p)))
        assert righe[0]['Tipo_Documento'] == 'TD04'


class TestRegoleDiDominio:

    def test_guardrail_note_con_importo(self, vision):
        """M27 — regola #2: '📝 NOTE E DICITURE' e' ammessa solo a importo zero.

        Il ramo Vision delega a `_applica_guardrail_note_con_importo`, con una
        logica DIVERSA da quella inline del path XML (:1180-1187): sono due
        implementazioni della stessa regola, entrambe da difendere.
        """
        with patch('services.ai_service._applica_guardrail_note_con_importo',
                   return_value='Da Classificare') as m_guard:
            righe = vision(_FakeOpenAI(json.dumps(PAYLOAD_OK)),
                           categoria='📝 NOTE E DICITURE')
        assert m_guard.called, "il guardrail deve essere interrogato"
        assert righe[0]['Categoria'] == 'Da Classificare'
        assert righe[0]['needs_review'] is True

    def test_note_a_importo_zero_restano_note(self, vision):
        payload = json.loads(json.dumps(PAYLOAD_OK))
        payload['righe'][0].update({'totale': 0, 'prezzo_unitario': 0, 'quantita': 0})
        righe = vision(_FakeOpenAI(json.dumps(payload)), categoria='📝 NOTE E DICITURE')
        assert righe[0]['Categoria'] == '📝 NOTE E DICITURE'

    def test_categoria_non_riconosciuta_resta_da_classificare(self, vision):
        """Regola #1: nessun fallback travestito in una categoria inventata."""
        righe = vision(_FakeOpenAI(json.dumps(PAYLOAD_OK)), categoria='Da Classificare')
        assert righe[0]['Categoria'] == 'Da Classificare'


class TestQuotaELimiti:

    def test_quota_esaurita_solleva(self, vision):
        """M26 — senza il raise il cliente consumerebbe API oltre il limite."""
        from services.invoice_service import VisionDailyLimitExceededError
        quota = MagicMock(return_value={'is_exceeded': True, 'used': 25, 'limit': 25})
        with pytest.raises(VisionDailyLimitExceededError) as exc:
            vision(_FakeOpenAI(json.dumps(PAYLOAD_OK)), quota=quota)
        assert exc.value.used == 25
        assert exc.value.limit == 25
        assert exc.value.ristorante_id == 'rist-1'

    def test_quota_disponibile_prosegue(self, vision):
        quota = MagicMock(return_value={'is_exceeded': False, 'used': 1, 'limit': 25})
        righe = vision(_FakeOpenAI(json.dumps(PAYLOAD_OK)), quota=quota)
        assert len(righe) == 1

    def test_errore_nel_check_quota_prosegue_senza_blocco(self, vision):
        """Fail-open deliberato (`:1407-1408`): il test descrive il
        comportamento ATTUALE, non lo certifica come desiderabile. Se un domani
        si decidesse di bloccare, questo test cade apposta e obbliga a
        prendere la decisione consapevolmente."""
        quota = MagicMock(side_effect=RuntimeError("quota service down"))
        righe = vision(_FakeOpenAI(json.dumps(PAYLOAD_OK)), quota=quota)
        assert len(righe) == 1

    def test_admin_bypassa_il_controllo_quota(self, vision):
        quota = MagicMock(return_value={'is_exceeded': True, 'used': 99, 'limit': 25})
        righe = vision(_FakeOpenAI(json.dumps(PAYLOAD_OK)),
                       session={'user_is_admin': True}, quota=quota)
        assert len(righe) == 1
        assert not quota.called

    def test_file_oltre_20mb_rifiutato(self, vision):
        """M25 — oltre ~20 MB la richiesta inline a OpenAI fallisce comunque:
        meglio scartare subito che pagare una chiamata destinata all'errore."""
        client = _FakeOpenAI(json.dumps(PAYLOAD_OK))
        righe = vision(client, file_caricato=_file(size=21 * 1024 * 1024))
        assert righe == []
        assert not client.chiamate.called, "non deve nemmeno chiamare l'AI"

    def test_file_appena_sotto_il_limite_passa(self, vision):
        righe = vision(_FakeOpenAI(json.dumps(PAYLOAD_OK)),
                       file_caricato=_file(size=20 * 1024 * 1024))
        assert len(righe) == 1


class TestRisposteMalformate:
    """Nota di metodo (mutazioni verificate il 10/8/2026).

    La gestione delle risposte rotte ha DUE strati: l'`except
    json.JSONDecodeError` dedicato (:1518) e l'`except Exception` globale
    (:1706). Disattivandone uno solo i test restano verdi — non perche' siano
    deboli, ma perche' l'altro strato produce lo stesso risultato osservabile
    (`[]`). La mutazione che li abbatte e' quella su ENTRAMBI, e allora cadono
    i 4 test di questa classe.
    """

    def test_json_troncato_restituisce_lista_vuota(self, vision):
        """M28 — con `max_tokens=4000` una fattura lunga puo' tornare troncata:
        deve degradare a zero righe, non far esplodere l'upload.

        Il payload va troncato davvero: la prima versione tagliava a 60 caratteri
        un JSON che ne conta 35, quindi restava valido e il test era verde per
        il motivo sbagliato — la mutazione su `except json.JSONDecodeError`
        restava verde e lo ha rivelato.
        """
        completo = json.dumps(PAYLOAD_OK)
        troncato = completo[: len(completo) // 2]
        with pytest.raises(json.JSONDecodeError):
            json.loads(troncato)  # il payload di prova deve essere davvero rotto
        assert vision(_FakeOpenAI(troncato)) == []

    def test_risposta_vuota(self, vision):
        assert vision(_FakeOpenAI(None)) == []

    def test_testo_libero_non_json(self, vision):
        assert vision(_FakeOpenAI("Mi dispiace, non riesco a leggere il documento.")) == []

    def test_json_senza_chiave_righe(self, vision):
        assert vision(_FakeOpenAI(json.dumps({"fornitore": "METRO"}))) == []

    def test_errore_del_client_openai_non_propaga(self, vision):
        """L'except globale `:1698-1701`: un guasto dell'AI non deve
        interrompere l'upload degli altri file del batch."""
        client = _FakeOpenAI(json.dumps(PAYLOAD_OK))
        client.chat.completions.create.side_effect = RuntimeError("API down")
        assert vision(client) == []

    def test_base64_fallito_restituisce_vuoto(self, vision):
        from services.invoice_service import estrai_dati_da_scontrino_vision
        mock_st = MagicMock()
        mock_st.session_state.get = lambda k, d=None: {'ristorante_id': None}.get(k, d)
        with patch('services.invoice_service.st', mock_st), \
             patch('services.invoice_service.converti_in_base64', return_value=None):
            assert estrai_dati_da_scontrino_vision(_file(), _FakeOpenAI("{}")) == []


class TestTrackingCosti:

    def test_uso_ai_tracciato(self, vision):
        track = MagicMock()
        vision(_FakeOpenAI(json.dumps(PAYLOAD_OK)), track=track)
        assert track.called
        kw = track.call_args.kwargs
        assert kw['operation_type'] == 'pdf'
        assert kw['prompt_tokens'] == 1000
        assert kw['metadata']['source'] == 'vision-upload'

    def test_tracking_fallito_non_perde_le_righe(self, vision):
        """Il tracking e' contabilita' interna: un suo errore non deve far
        perdere una fattura gia' estratta."""
        track = MagicMock(side_effect=RuntimeError("tracking down"))
        righe = vision(_FakeOpenAI(json.dumps(PAYLOAD_OK)), track=track)
        assert len(righe) == 1

    def test_senza_usage_nessun_tracking(self, vision):
        track = MagicMock()
        client = _FakeOpenAI(json.dumps(PAYLOAD_OK), usage=False)
        righe = vision(client, track=track)
        assert len(righe) == 1
        assert not track.called
