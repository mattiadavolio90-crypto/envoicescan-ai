-- Fase A migrazione Agenda: la pagina Strumenti e' stata divisa in due voci
-- di sidebar separate: "Agenda" (appuntamenti/spese/personale) e "Strumenti"
-- (foodcost/inventario). La sidebar usa flag distinti: il nuovo flag "agenda"
-- e il preesistente "workspace".
--
-- Chi aveva "workspace" abilitato deve continuare a vedere quelle funzioni:
-- propaghiamo "agenda": true a tutti gli utenti che hanno gia' "workspace": true
-- in pagine_abilitate. Gli utenti con pagine_abilitate = NULL vedono tutto per
-- default (vedi _normalize_pagine nel worker), quindi non vanno toccati.
--
-- Idempotente: se "agenda" e' gia' presente, jsonb_set lo riscrive allo stesso
-- valore senza effetti collaterali.

UPDATE public.users
SET pagine_abilitate = jsonb_set(pagine_abilitate, '{agenda}', 'true'::jsonb, true)
WHERE pagine_abilitate IS NOT NULL
  AND jsonb_typeof(pagine_abilitate) = 'object'
  AND (pagine_abilitate ->> 'workspace') = 'true';
