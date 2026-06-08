/* Cattura globale dell'evento beforeinstallprompt.

   Chrome (Android) emette beforeinstallprompt UNA SOLA VOLTA, all'inizio del
   caricamento pagina, spesso PRIMA che React idrati e monti il componente
   InstallPrompt. Se nessuno lo sta ascoltando in quel momento, l'evento e'
   perso e il banner "Installa ONEFLUX" non appare mai.

   Questo script gira con strategy="beforeInteractive" (prima dell'idratazione)
   e si limita a:
     1. preventDefault() sull'evento (cosi' Chrome non mostra il mini-infobar
        nativo e lascia decidere a noi quando proporre l'installazione);
     2. conservare l'evento su window.__oneflux_bip;
     3. ri-emettere un CustomEvent "oneflux:installable" per chi monta dopo.

   InstallPrompt al mount legge window.__oneflux_bip (se l'evento e' gia'
   arrivato) e in parallelo ascolta "oneflux:installable" (se arriva dopo).
   Cosi' la cattura e' indipendente dal timing dell'idratazione. */
(function () {
  if (window.__oneflux_bip_capture) return;
  window.__oneflux_bip_capture = true;
  window.__oneflux_bip = null;

  window.addEventListener("beforeinstallprompt", function (e) {
    e.preventDefault();
    window.__oneflux_bip = e;
    try {
      window.dispatchEvent(new CustomEvent("oneflux:installable"));
    } catch (_) {
      /* CustomEvent non disponibile: InstallPrompt leggera' comunque __oneflux_bip al mount */
    }
  });

  window.addEventListener("appinstalled", function () {
    window.__oneflux_bip = null;
  });
})();
