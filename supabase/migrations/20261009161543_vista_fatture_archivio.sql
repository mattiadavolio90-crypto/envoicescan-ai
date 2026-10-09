-- Gestione Fatture si apre su «Archivio fatture» (Mattia, 09/10/2026).
--
-- La colonna nasceva con DEFAULT 'agenda' (20260912083352): chi non ha mai
-- scelto una vista e chi ha scelto «Da pagare» (oggi «Scadenzario») hanno lo
-- stesso valore e non si distinguono. Misurato sul live il 09/10: 6 account e
-- 1 sotto-utente su 'agenda'. Decisione di Mattia: tutti su Archivio — chi
-- vuole lo Scadenzario lo riapre con un clic e la scelta resta salvata.
--
-- Le chiavi non cambiano (agenda/calendario/lista_mensile): cambia solo il
-- default e il valore di chi era sul vecchio default.

ALTER TABLE public.users ALTER COLUMN vista_fatture SET DEFAULT 'lista_mensile';
ALTER TABLE public.sotto_utenti ALTER COLUMN vista_fatture SET DEFAULT 'lista_mensile';

UPDATE public.users SET vista_fatture = 'lista_mensile' WHERE vista_fatture = 'agenda';
UPDATE public.sotto_utenti SET vista_fatture = 'lista_mensile' WHERE vista_fatture = 'agenda';
