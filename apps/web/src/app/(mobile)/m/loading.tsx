// Loading mobile: il logo con i due anelli che si espandono in continuazione,
// lo stesso effetto dell'overlay di login (classi oneflux-login-* globali).
export default function Loading() {
  return (
    <div className="flex min-h-[60vh] w-full items-center justify-center">
      <div className="oneflux-login-stage" style={{ width: 140, height: 140 }}>
        <span className="oneflux-login-ring" />
        <span className="oneflux-login-ring" />
        <span className="oneflux-login-mark text-primary" style={{ width: 96, height: 96 }}>
          <svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className="size-full">
            <circle cx="50" cy="50" r="42" stroke="currentColor" strokeWidth="6" fill="none" />
            <circle cx="50" cy="50" r="31" stroke="currentColor" strokeWidth="2.5" fill="none" />
            <g className="oneflux-spinner-x" style={{ transformOrigin: "50% 50%" }}>
              <path d="M36 36 C48 44 48 56 64 64" stroke="currentColor" strokeWidth="7" strokeLinecap="round" fill="none" />
              <path d="M64 36 C52 44 52 56 36 64" stroke="currentColor" strokeWidth="7" strokeLinecap="round" fill="none" />
            </g>
          </svg>
        </span>
      </div>
    </div>
  );
}
