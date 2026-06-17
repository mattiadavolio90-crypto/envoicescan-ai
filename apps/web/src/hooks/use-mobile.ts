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
