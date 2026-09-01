"""Esegue moduli TypeScript di produzione dentro pytest, senza runner frontend.

`apps/web/` non ha un test runner (decisione del punto 9 del ciclo 2026-08: un
runner in `apps/web/package.json` farebbe partire il deploy Vercel a ogni merge
di un test, perche' `deploy-vercel.yml` scatta su `paths: apps/web/**`). I test
sulla logica pura del frontend vivono quindi qui, in pytest, e importano il
modulo **vero** con node.

Tecnica: `--experimental-strip-types` toglie le annotazioni e `registerHooks`
risolve l'alias `@/` di `tsconfig.json`. Sostituisce l'estrazione con regex dei
due test storici (password policy, open redirect), che aveva due limiti:

1. spogliava i tipi con una `.replace()` letterale della firma. Cambiando un
   parametro la replace non matcha, non fallisce, e node muore con un
   SyntaxError che non dice qual e' il problema vero;
2. non attraversava gli `import`. Per questo `categorie-spesa.ts` — che importa
   `CATEGORIE_TUTTE` da `@/lib/admin` — era irraggiungibile.

**Cosa NON copre.** Solo logica pura in moduli senza React: niente rendering,
hook, stato, effetti, `useMemo`, routing, CSS, accessibilita', integrazione API
reale. Fuori da `apps/web/src/lib/` non arriva. Scritto qui perche' altrimenti
la copertura frontend sembra piu' ampia di quella che e'.

**Rete.** Il ban di rete del conftest patcha il processo Python, non il
sottoprocesso node: `globalThis.fetch` viene quindi stubbato a `throw` nel
prologo. Testare solo moduli senza side-effect all'import.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable

import pytest

WEB_SRC = Path(__file__).resolve().parents[1] / "apps/web/src"

# Il risultato viaggia su un marcatore invece che su stdout nudo: node stampa
# warning propri (MODULE_TYPELESS_PACKAGE_JSON) e appoggiarsi a "stdout pulito"
# e' una scommessa sulla versione di node.
_MARCATORE = "__RES__"


def node_o_fallisci():
    """Skip in locale se manca node, ma **fallimento in CI**.

    Uno `skipif` trasformerebbe questi test in skip verdi: nessuno li guarda e
    la regressione passa. In CI un ambiente senza node e' un guasto da
    riparare, non un test da saltare. `tests.yml` dichiara node 22 apposta.
    """
    if shutil.which("node"):
        return None
    if os.getenv("CI"):
        return pytest.fail(
            "node non disponibile in CI: questi test non possono essere saltati "
            "in silenzio. Aggiungi actions/setup-node a .github/workflows/tests.yml",
            pytrace=False,
        )
    pytest.skip("serve node per eseguire il codice client")


def _prologo(modulo: str, richiede: Iterable[str]) -> str:
    attesi = json.dumps(list(richiede))
    return f"""
import module from "node:module";
const SRC = {json.dumps(str(WEB_SRC) + "/")};
module.registerHooks({{
  resolve(spec, ctx, next) {{
    if (spec.startsWith("@/")) return next(SRC + spec.slice(2) + ".ts", ctx);
    return next(spec, ctx);
  }},
}});
globalThis.fetch = () => {{ throw new Error("rete vietata nei test"); }};
const m = await import(SRC + {json.dumps(modulo)} + ".ts");
for (const nome of {attesi}) {{
  if (typeof m[nome] !== "function") {{
    console.error(
      "esportazione `" + nome + "` sparita da {modulo}: rinominata o spostata? " +
      "Aggiorna il test, non cancellarlo."
    );
    process.exit(3);
  }}
}}
const input = process.argv[1] ? JSON.parse(process.argv[1]) : null;
const emit = (v) => console.log({json.dumps(_MARCATORE)} + JSON.stringify(v));
"""


def esegui_ts(
    modulo: str,
    espressione: str,
    argomento: Any = None,
    tz: str | None = None,
    richiede: Iterable[str] = (),
) -> Any:
    """Importa `modulo` da apps/web/src ed esegue `espressione`.

    `modulo` e' il path relativo senza estensione (es. "lib/scadenziario").
    Dentro `espressione` sono disponibili `m` (il modulo), `input` (l'argomento
    deserializzato) ed `emit(valore)` per restituire il risultato.

    `richiede` elenca le funzioni che devono esistere: se una e' stata
    rinominata il test **fallisce** con un messaggio esplicito invece di
    passare per caso o di skippare.
    """
    node_o_fallisci()

    sorgente = WEB_SRC / f"{modulo}.ts"
    assert sorgente.exists(), (
        f"{sorgente} non esiste: se il modulo e' stato spostato o rinominato "
        "aggiorna questo test invece di cancellarlo."
    )

    script = _prologo(modulo, richiede) + espressione
    env = dict(os.environ)
    if tz:
        env["TZ"] = tz

    esito = subprocess.run(
        [
            "node",
            "--experimental-strip-types",
            "--input-type=module",
            "-e",
            script,
            # `--` e' obbligatorio, non cosmetico: senza, un argomento che
            # inizia con `-` (un numero negativo: `-2.675`) viene letto da node
            # come flag e il processo esce con rc=9 e stderr vuoto — un
            # fallimento che sembra un errore del modulo sotto test.
            "--",
            json.dumps(argomento),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert esito.returncode == 0, (
        f"il modulo client {modulo} non gira (rc={esito.returncode}):\n{esito.stderr}"
    )

    for riga in esito.stdout.splitlines():
        if riga.startswith(_MARCATORE):
            return json.loads(riga[len(_MARCATORE):])
    raise AssertionError(
        f"{modulo} non ha prodotto un risultato: manca una chiamata a emit()?\n"
        f"stdout: {esito.stdout!r}\nstderr: {esito.stderr}"
    )
