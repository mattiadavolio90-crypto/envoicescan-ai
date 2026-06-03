/* Boot overlay PWA — creato e rimosso interamente da questo script, FUORI da
   React. Gira con strategy="beforeInteractive" (prima dell'idratazione).

   Perche' non e' nel JSX: un nodo renderizzato da React e poi rimosso da uno
   script esterno corrompeva l'albero idratato e faceva fallire la prima
   navigazione client ("this page couldn't load" al primo tocco dopo
   l'apertura). Creandolo qui, React non lo vede mai: nessun nodo conteso.

   L'overlay viene mostrato SOLO in modalita' standalone (PWA installata), per
   coprire lo splash statico del sistema con l'animazione di brand, e rimosso
   dopo ~1.4s. In browser normale non viene nemmeno creato. */
(function () {
  try {
    var standalone =
      (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches) ||
      window.navigator.standalone === true;
    if (!standalone) return;

    var NS = "http://www.w3.org/2000/svg";

    function svgEl(name, attrs) {
      var el = document.createElementNS(NS, name);
      for (var k in attrs) el.setAttribute(k, attrs[k]);
      return el;
    }

    function build() {
      // Evita doppioni se lo script venisse eseguito due volte.
      if (document.getElementById("oneflux-boot")) return;

      var overlay = document.createElement("div");
      overlay.id = "oneflux-boot";
      overlay.setAttribute("aria-hidden", "true");

      var stage = document.createElement("div");
      stage.className = "oneflux-login-stage";
      stage.style.width = "160px";
      stage.style.height = "160px";

      var ring1 = document.createElement("span");
      ring1.className = "oneflux-login-ring";
      var ring2 = document.createElement("span");
      ring2.className = "oneflux-login-ring";

      var mark = document.createElement("span");
      mark.className = "oneflux-login-mark text-primary";
      mark.style.width = "104px";
      mark.style.height = "104px";

      var svg = svgEl("svg", { viewBox: "0 0 100 100", fill: "none", class: "size-full" });
      svg.appendChild(svgEl("circle", { cx: "50", cy: "50", r: "42", stroke: "currentColor", "stroke-width": "6", fill: "none" }));
      svg.appendChild(svgEl("circle", { cx: "50", cy: "50", r: "31", stroke: "currentColor", "stroke-width": "2.5", fill: "none" }));

      var g = svgEl("g", { class: "oneflux-spinner-x" });
      g.style.transformOrigin = "50% 50%";
      g.appendChild(svgEl("path", { d: "M36 36 C48 44 48 56 64 64", stroke: "currentColor", "stroke-width": "7", "stroke-linecap": "round", fill: "none" }));
      g.appendChild(svgEl("path", { d: "M64 36 C52 44 52 56 36 64", stroke: "currentColor", "stroke-width": "7", "stroke-linecap": "round", fill: "none" }));
      svg.appendChild(g);

      mark.appendChild(svg);
      stage.appendChild(ring1);
      stage.appendChild(ring2);
      stage.appendChild(mark);
      overlay.appendChild(stage);

      // Lo agganciamo a <html>, fratello del <body>: cosi' e' del tutto fuori
      // dal sottoalbero che React idrata.
      document.documentElement.appendChild(overlay);

      // Fade-out dopo ~1s, poi rimozione. La classe app-ready sul body fa
      // partire la transizione di opacita' (vedi globals.css). Niente di tutto
      // questo tocca nodi gestiti da React.
      window.setTimeout(function () {
        if (document.body) document.body.classList.add("app-ready");
        window.setTimeout(function () {
          var o = document.getElementById("oneflux-boot");
          if (o && o.parentNode) o.parentNode.removeChild(o);
        }, 400);
      }, 1000);
    }

    // <html> esiste sempre quando gira lo script; <body> potrebbe non esistere
    // ancora, ma noi agganciamo a <html> e tocchiamo document.body solo nel
    // setTimeout (a quel punto esiste di sicuro).
    build();
  } catch (e) {
    var o = document.getElementById("oneflux-boot");
    if (o && o.parentNode) o.parentNode.removeChild(o);
  }
})();
