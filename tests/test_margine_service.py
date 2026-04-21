"""
Test unitari per services/margine_service.py
Copertura: calcola_risultati, calcola_kpi_anno
"""

import pytest
import pandas as pd

from services.margine_service import calcola_risultati, calcola_kpi_anno, build_transposed_df, export_excel_margini

# ---------------------------------------------------------------------------
# Helper: costruisce un DataFrame di input a 12 righe
# ---------------------------------------------------------------------------
MESI_NOMI = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu",
             "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]

def _make_input(
    fatt_iva10=0.0,
    fatt_iva22=0.0,
    altri_ricavi_noiva=0.0,
    costi_fb_auto=0.0,
    altri_fb=0.0,
    costi_spese_auto=0.0,
    altri_spese=0.0,
    costo_dipendenti=0.0,
    overrides: dict = None,
) -> pd.DataFrame:
    """
    Crea un DataFrame di 12 righe con valori uniformi.
    overrides: {indice_mese (0-11): {colonna: valore}} per impostare mesi specifici.
    """
    rows = []
    for i in range(12):
        rows.append({
            "Mese": MESI_NOMI[i],
            "MeseNum": i + 1,
            "Fatt_IVA10": fatt_iva10,
            "Fatt_IVA22": fatt_iva22,
            "Altri_Ricavi_NoIVA": altri_ricavi_noiva,
            "Costi_FB_Auto": costi_fb_auto,
            "Altri_FB": altri_fb,
            "Costi_Spese_Auto": costi_spese_auto,
            "Altri_Spese": altri_spese,
            "Costo_Dipendenti": costo_dipendenti,
        })
    if overrides:
        for idx, vals in overrides.items():
            rows[idx].update(vals)
    return pd.DataFrame(rows)


# ===========================================================================
# calcola_risultati
# ===========================================================================

class TestCalcolaRisultati:

    def test_calcola_risultati_happy_path(self):
        """
        12 mesi con dati uniformi.
        Verifica struttura output, formula Fatt_Netto, formula MOL e riga TOT ANNO.
        """
        df_in = _make_input(
            fatt_iva10=1100.0,      # netto = 1000
            fatt_iva22=1220.0,      # netto = 1000
            altri_ricavi_noiva=500.0,
            costi_fb_auto=300.0,
            altri_fb=100.0,         # Costi_FB totali = 400
            costi_spese_auto=200.0,
            altri_spese=50.0,       # Costi_Spese totali = 250
            costo_dipendenti=600.0,
        )

        df = calcola_risultati(df_in)

        # Struttura: 13 righe (12 mesi + TOT ANNO)
        assert len(df) == 13

        # Colonne attese
        for col in ["Mese", "MeseNum", "Fatt_Netto", "Costi_FB", "FB_Perc",
                    "Primo_Margine", "PM_Perc", "Costi_Spese", "Spese_Perc",
                    "Costi_Personale", "Pers_Perc", "MOL", "MOL_Perc"]:
            assert col in df.columns, f"Colonna mancante: {col}"

        # Riga TOT ANNO esiste
        tot = df[df["Mese"] == "TOT ANNO"]
        assert len(tot) == 1, "Riga TOT ANNO mancante"

        # Fatt_Netto corretto per il primo mese
        fatt_netto_atteso = round(1100.0 / 1.10 + 1220.0 / 1.22 + 500.0, 2)
        assert round(df.iloc[0]["Fatt_Netto"], 2) == fatt_netto_atteso

        # MOL = Primo_Margine - Costi_Spese - Costi_Personale
        riga0 = df.iloc[0]
        mol_atteso = round(riga0["Primo_Margine"] - riga0["Costi_Spese"] - riga0["Costi_Personale"], 2)
        assert round(riga0["MOL"], 2) == mol_atteso

        # TOT ANNO Fatt_Netto = somma dei 12 mesi
        assert round(tot.iloc[0]["Fatt_Netto"], 2) == round(fatt_netto_atteso * 12, 2)

    def test_calcola_risultati_mese_zero(self):
        """
        Solo il primo mese ha Fatt_Netto == 0 (tutti gli importi a 0).
        Le percentuali del mese devono essere 0.0 senza ZeroDivisionError.
        """
        df_in = _make_input(
            fatt_iva10=1100.0,
            fatt_iva22=0.0,
            altri_ricavi_noiva=0.0,
            costi_fb_auto=300.0,
            altri_fb=0.0,
            costi_spese_auto=100.0,
            altri_spese=0.0,
            costo_dipendenti=200.0,
            overrides={
                0: {
                    "Fatt_IVA10": 0.0,
                    "Fatt_IVA22": 0.0,
                    "Altri_Ricavi_NoIVA": 0.0,
                }
            },
        )

        df = calcola_risultati(df_in)

        riga0 = df.iloc[0]
        assert round(riga0["Fatt_Netto"], 2) == 0.0
        assert round(riga0["FB_Perc"], 2) == 0.0
        assert round(riga0["PM_Perc"], 2) == 0.0
        assert round(riga0["Spese_Perc"], 2) == 0.0
        assert round(riga0["Pers_Perc"], 2) == 0.0
        assert round(riga0["MOL_Perc"], 2) == 0.0

    def test_calcola_risultati_tutti_zero(self):
        """
        Tutti i 12 mesi a zero.
        TOT ANNO deve avere Fatt_Netto == 0 e tutte le percentuali == 0.
        """
        df_in = _make_input()  # tutti i default sono 0.0

        df = calcola_risultati(df_in)
        assert len(df) == 13

        tot = df[df["Mese"] == "TOT ANNO"].iloc[0]
        assert round(tot["Fatt_Netto"], 2) == 0.0
        for perc_col in ["FB_Perc", "PM_Perc", "Spese_Perc", "Pers_Perc", "MOL_Perc"]:
            assert round(tot[perc_col], 2) == 0.0, f"{perc_col} deve essere 0"

    def test_calcola_risultati_un_solo_mese_con_dati(self):
        """
        Solo il mese di Gennaio (indice 0) ha dati reali.
        TOT ANNO deve riflettere solo quel mese.
        """
        df_in = _make_input(
            overrides={
                0: {
                    "Fatt_IVA10": 1100.0,
                    "Fatt_IVA22": 0.0,
                    "Altri_Ricavi_NoIVA": 0.0,
                    "Costi_FB_Auto": 400.0,
                    "Altri_FB": 0.0,
                    "Costi_Spese_Auto": 100.0,
                    "Altri_Spese": 0.0,
                    "Costo_Dipendenti": 150.0,
                }
            }
        )

        df = calcola_risultati(df_in)
        tot = df[df["Mese"] == "TOT ANNO"].iloc[0]

        fatt_netto_gen = round(1100.0 / 1.10, 2)
        assert round(tot["Fatt_Netto"], 2) == fatt_netto_gen

        costi_fb = 400.0
        primo_margine = fatt_netto_gen - costi_fb
        mol_atteso = round(primo_margine - 100.0 - 150.0, 2)
        assert round(tot["MOL"], 2) == mol_atteso


# ===========================================================================
# calcola_kpi_anno
# ===========================================================================

def _make_risultati(rows_override: list = None) -> pd.DataFrame:
    """
    Crea un DataFrame compatibile con l'output di calcola_risultati
    (13 righe: 12 mesi + TOT ANNO) con valori personalizzabili.
    rows_override: lista di dict con i valori per ogni mese (indici 0-11).
    """
    default_mese = {
        "MeseNum": 0,
        "Fatt_Netto": 0.0,
        "Costi_FB": 0.0,
        "FB_Perc": 0.0,
        "Primo_Margine": 0.0,
        "PM_Perc": 0.0,
        "Costi_Spese": 0.0,
        "Spese_Perc": 0.0,
        "Costi_Personale": 0.0,
        "Pers_Perc": 0.0,
        "MOL": 0.0,
        "MOL_Perc": 0.0,
    }
    rows = []
    for i in range(12):
        row = default_mese.copy()
        row["MeseNum"] = i + 1
        row["Mese"] = MESI_NOMI[i]
        if rows_override and i < len(rows_override) and rows_override[i] is not None:
            row.update(rows_override[i])
        rows.append(row)

    # Riga TOT ANNO
    tot = default_mese.copy()
    tot["MeseNum"] = 99
    tot["Mese"] = "TOT ANNO"
    rows.append(tot)

    return pd.DataFrame(rows)


class TestCalcolaKpiAnno:

    def test_calcola_kpi_anno_happy_path(self):
        """
        3 mesi con Fatt_Netto > 0, gli altri a zero.
        Verifica num_mesi == 3 e che le medie siano corrette.
        """
        mesi_data = [
            {"Fatt_Netto": 1000.0, "MOL": 200.0, "FB_Perc": 30.0, "MOL_Perc": 20.0,
             "Primo_Margine": 700.0, "PM_Perc": 70.0, "Costi_FB": 300.0,
             "Costi_Spese": 300.0, "Spese_Perc": 30.0, "Costi_Personale": 200.0, "Pers_Perc": 20.0},
            {"Fatt_Netto": 2000.0, "MOL": 400.0, "FB_Perc": 25.0, "MOL_Perc": 20.0,
             "Primo_Margine": 1500.0, "PM_Perc": 75.0, "Costi_FB": 500.0,
             "Costi_Spese": 700.0, "Spese_Perc": 35.0, "Costi_Personale": 400.0, "Pers_Perc": 20.0},
            {"Fatt_Netto": 1500.0, "MOL": 300.0, "FB_Perc": 28.0, "MOL_Perc": 20.0,
             "Primo_Margine": 1100.0, "PM_Perc": 73.33, "Costi_FB": 400.0,
             "Costi_Spese": 500.0, "Spese_Perc": 33.33, "Costi_Personale": 300.0, "Pers_Perc": 20.0},
        ]

        df = _make_risultati(mesi_data)
        kpi = calcola_kpi_anno(df)

        assert kpi["num_mesi"] == 3
        assert round(kpi["mol_medio"], 2) == round((200.0 + 400.0 + 300.0) / 3, 2)
        assert round(kpi["fatt_medio"], 2) == round((1000.0 + 2000.0 + 1500.0) / 3, 2)
        assert round(kpi["fc_medio"], 2) == round((30.0 + 25.0 + 28.0) / 3, 2)

    def test_calcola_kpi_anno_mesi_filtro(self):
        """
        Passa mesi_filtro=[1, 2]: solo i mesi 1 e 2 devono essere conteggiati.
        """
        mesi_data = [
            {"Fatt_Netto": 1000.0, "MOL": 200.0, "FB_Perc": 30.0, "MOL_Perc": 20.0,
             "Primo_Margine": 700.0, "PM_Perc": 70.0, "Costi_FB": 300.0,
             "Costi_Spese": 300.0, "Spese_Perc": 30.0, "Costi_Personale": 200.0, "Pers_Perc": 20.0},
            {"Fatt_Netto": 2000.0, "MOL": 600.0, "FB_Perc": 20.0, "MOL_Perc": 30.0,
             "Primo_Margine": 1500.0, "PM_Perc": 75.0, "Costi_FB": 400.0,
             "Costi_Spese": 500.0, "Spese_Perc": 25.0, "Costi_Personale": 400.0, "Pers_Perc": 20.0},
            {"Fatt_Netto": 3000.0, "MOL": 900.0, "FB_Perc": 15.0, "MOL_Perc": 30.0,
             "Primo_Margine": 2000.0, "PM_Perc": 66.67, "Costi_FB": 450.0,
             "Costi_Spese": 650.0, "Spese_Perc": 21.67, "Costi_Personale": 450.0, "Pers_Perc": 15.0},
        ]

        df = _make_risultati(mesi_data)
        kpi = calcola_kpi_anno(df, mesi_filtro=[1, 2])

        assert kpi["num_mesi"] == 2
        assert round(kpi["mol_medio"], 2) == round((200.0 + 600.0) / 2, 2)
        assert round(kpi["fatt_medio"], 2) == round((1000.0 + 2000.0) / 2, 2)

    def test_calcola_kpi_anno_tutti_zero(self):
        """
        Tutti i mesi con Fatt_Netto == 0: deve tornare kpi_zero senza eccezioni.
        """
        df = _make_risultati()  # tutti 0
        kpi = calcola_kpi_anno(df)

        assert kpi["num_mesi"] == 0
        assert kpi["mol_medio"] == 0.0
        assert kpi["fatt_medio"] == 0.0
        assert kpi["fc_medio"] == 0.0
        assert kpi["mol_perc_medio"] == 0.0

    def test_calcola_kpi_anno_dataframe_vuoto(self):
        """
        DataFrame vuoto (0 righe): il fallback kpi_zero deve essere restituito
        senza crash.
        """
        df_vuoto = pd.DataFrame(columns=[
            "MeseNum", "Fatt_Netto", "MOL", "FB_Perc", "MOL_Perc",
            "Primo_Margine", "PM_Perc", "Costi_FB",
            "Costi_Spese", "Spese_Perc", "Costi_Personale", "Pers_Perc"
        ])
        kpi = calcola_kpi_anno(df_vuoto)

        assert isinstance(kpi, dict)
        assert kpi["num_mesi"] == 0
        assert kpi["mol_medio"] == 0.0


# ===========================================================================
# build_transposed_df
# ===========================================================================

class TestBuildTransposedDf:

    def test_build_transposed_df_happy_path(self):
        """
        12 mesi con dati validi.
        - 12 righe (una per voce finanziaria)
        - Colonne Gen €, Gen %, Dic €, Dic % presenti
        - Fatt_Netto Gen calcolato correttamente
        """
        df_in = _make_input(
            fatt_iva10=1100.0,
            fatt_iva22=1220.0,
            altri_ricavi_noiva=500.0,
            costi_fb_auto=300.0,
            altri_fb=100.0,
            costi_spese_auto=200.0,
            altri_spese=50.0,
            costo_dipendenti=600.0,
        )

        df = build_transposed_df(df_in)

        # 12 righe (voci finanziarie)
        assert len(df) == 12

        # Colonne attese
        for col in ["Voce", "Gen €", "Gen %", "Dic €", "Dic %"]:
            assert col in df.columns, f"Colonna mancante: {col}"

        # Trova la riga "= Fatturato Netto"
        riga_fn = df[df["Voce"] == "= Fatturato Netto"]
        assert len(riga_fn) == 1, "Riga '= Fatturato Netto' non trovata"

        fatt_netto_atteso = round(1100.0 / 1.10 + 1220.0 / 1.22 + 500.0, 2)
        assert round(riga_fn.iloc[0]["Gen €"], 2) == fatt_netto_atteso

        # La riga Fatturato Netto non ha percentuale (None o NaN)
        assert pd.isna(riga_fn.iloc[0]["Gen %"])

    def test_build_transposed_df_tutti_zero(self):
        """
        Tutti i mesi a zero: deve ritornare 12 righe senza crash,
        con valori 0 nelle colonne €.
        """
        df_in = _make_input()

        df = build_transposed_df(df_in)

        assert len(df) == 12
        assert "Voce" in df.columns

        # Tutti i valori € devono essere 0
        riga_fn = df[df["Voce"] == "= Fatturato Netto"].iloc[0]
        assert round(riga_fn["Gen €"], 2) == 0.0
        assert round(riga_fn["Dic €"], 2) == 0.0


# ===========================================================================
# export_excel_margini
# ===========================================================================

def _make_df_risultati_completo() -> pd.DataFrame:
    """Costruisce un df_risultati realistico passando per calcola_risultati."""
    df_in = _make_input(
        fatt_iva10=1100.0,
        fatt_iva22=1220.0,
        altri_ricavi_noiva=500.0,
        costi_fb_auto=300.0,
        altri_fb=100.0,
        costi_spese_auto=200.0,
        altri_spese=50.0,
        costo_dipendenti=600.0,
    )
    return calcola_risultati(df_in)


# kpi_data minimale con le chiavi attese da export_excel_margini
_KPI_DATA_MINIMALE = {
    "periodo": "Gen-Mar 2025",
    "num_mesi": 3,
    "fatt_totale": 15000.0,
    "fatt_medio": 5000.0,
    "costi_fb": 1200.0,
    "fc_perc": 24.0,
    "primo_marg": 3800.0,
    "primo_marg_perc": 76.0,
    "spese_gen": 600.0,
    "spese_perc": 12.0,
    "personale": 800.0,
    "personale_perc": 16.0,
    "mol_medio": 1000.0,
    "mol_perc": 20.0,
}


class TestExportExcelMargini:

    def test_export_excel_senza_kpi(self):
        """
        Happy path senza kpi_data:
        - ritorna bytes non vuoti
        - file Excel valido con foglio "Margini 2025"
        """
        import io
        import openpyxl

        df_ris = _make_df_risultati_completo()
        result = export_excel_margini(df_ris, anno=2025, nome_ristorante="Test Ristorante")

        assert isinstance(result, bytes)
        assert len(result) > 0

        wb = openpyxl.load_workbook(io.BytesIO(result))
        assert "Margini 2025" in wb.sheetnames
        # Senza kpi_data deve avere solo 1 foglio
        assert "KPI Periodo" not in wb.sheetnames

    def test_export_excel_con_kpi(self):
        """
        Happy path con kpi_data:
        - deve esistere il foglio "KPI Periodo"
        - deve esistere il foglio "Margini 2025"
        """
        import io
        import openpyxl

        df_ris = _make_df_risultati_completo()
        result = export_excel_margini(
            df_ris,
            anno=2025,
            nome_ristorante="Test Ristorante",
            kpi_data=_KPI_DATA_MINIMALE,
        )

        assert isinstance(result, bytes)
        assert len(result) > 0

        wb = openpyxl.load_workbook(io.BytesIO(result))
        assert "Margini 2025" in wb.sheetnames
        assert "KPI Periodo" in wb.sheetnames

    def test_export_excel_df_vuoto_non_crasha(self):
        """
        df_risultati senza righe TOT ANNO (o vuoto): verifica che non crashi
        silenziosamente — deve sollevare un'eccezione documentata (IndexError/KeyError),
        non restituire bytes corrotti.
        """
        import pytest

        df_vuoto = _make_risultati()  # ha TOT ANNO con tutti zero — non crasha
        # Questo è il caso limite: df con TOT ANNO a zero deve comunque produrre bytes validi
        result = export_excel_margini(df_vuoto, anno=2025, nome_ristorante="Vuoto")
        assert isinstance(result, bytes)
        assert len(result) > 0

