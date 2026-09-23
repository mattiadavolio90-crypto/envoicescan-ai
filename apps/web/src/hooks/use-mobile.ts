import * as React from "react"
import { isPhoneViewport } from "@/lib/device"

const MOBILE_BREAKPOINT = 768

// "Mobile" = TELEFONO, non tablet. I tablet (iPad/Android tablet) restano
// sull'app desktop completa anche se stretti/verticali (vedi lib/device.ts).
export function useIsMobile() {
  const [isMobile, setIsMobile] = React.useState<boolean | undefined>(undefined)

  React.useEffect(() => {
    const mql = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`)
    const onChange = () => {
      setIsMobile(isPhoneViewport())
    }
    mql.addEventListener("change", onChange)
    setIsMobile(isPhoneViewport())
    return () => mql.removeEventListener("change", onChange)
  }, [])

  return !!isMobile
}

// Come `useIsMobile`, ma SENZA appiattire lo stato iniziale: torna `undefined`
// finche' il rilevamento non e' avvenuto (il valore vero arriva dall'effect,
// cioe' al secondo render).
//
// Serve a chi deve DECIDERE UNA VOLTA SOLA: `!!isMobile` rende il primo render
// indistinguibile da "non e' un telefono", e chi memorizza quella decisione
// finisce per registrarla su un falso. E' il difetto trovato dalla review del
// 23/09/2026: MobileRedirect consumava la decisione al primo render e al
// secondo — quello col valore vero — la trovava gia' presa, quindi i telefoni
// veri non venivano piu' rimbalzati su /m.
export function useIsMobileDetect(): boolean | undefined {
  const [isMobile, setIsMobile] = React.useState<boolean | undefined>(undefined)

  React.useEffect(() => {
    const mql = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`)
    const onChange = () => {
      setIsMobile(isPhoneViewport())
    }
    mql.addEventListener("change", onChange)
    setIsMobile(isPhoneViewport())
    return () => mql.removeEventListener("change", onChange)
  }, [])

  return isMobile
}
