/* Cattura globale dell'evento beforeinstallprompt.

   Chrome (Android) emette beforeinstallprompt UNA SOLA VOLTA, all'inizio del
   caricamento pagina, spesso PRIMA che React idrati e monti il componente
   InstallPrompt. Se nessuno lo sta ascoltando in quel momento, l'evento e'
   perso e il banner "Installa ONEFLUX" non appare mai.

   IMPORTANTE — perche' NON facciamo preventDefault() qui: chiamarlo sopprime il
   prompt nativo di Chrome OVUNQUE, anche dove il nostro banner custom non c'e'
   (es. /admin, /dashboard). Risultato: l'admin smetteva di vedere QUALSIASI
   proposta di installazione (il nativo soppresso, il custom assente perche'
   vive solo su /m). Quindi qui ci limitiamo a CONSERVARE l'evento, senza
   sopprimere il nativo. La soppressione (preventDefault) la fa SOLO
   InstallPrompt, e solo su /m dove esiste l'alternativa custom.

   Questo script gira con strategy="beforeInteractive" (prima dell'idratazione)
   e si limita a:
     1. conservare l'evento su window.__oneflux_bip;
     2. ri-emettere un CustomEvent "oneflux:installable" per chi monta dopo.

   InstallPrompt al mount legge window.__oneflux_bip (se l'evento e' gia'
   arrivato) e in parallelo ascolta "oneflux:installable" (se arriva dopo).
   Cosi' la cattura e' indipendente dal timing dell'idratazione. */
(function () {
  if (window.__oneflux_bip_capture) return;
  window.__oneflux_bip_capture = true;
  window.__oneflux_bip = null;

  window.addEventListener("beforeinstallprompt", function (e) {
    // NIENTE preventDefault qui: su pagine senza il nostro banner (es. /admin)
    // il prompt nativo di Chrome deve restare disponibile come prima.
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
