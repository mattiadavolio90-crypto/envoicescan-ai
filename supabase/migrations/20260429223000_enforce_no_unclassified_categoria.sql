-- Enforce: nessuna riga fatture può avere categoria vuota/null/Da Classificare
-- Obiettivo: hardening definitivo lato database (oltre ai guardrail applicativi).

alter table public.fatture
    drop constraint if exists fatture_categoria_not_unclassified_chk;

alter table public.fatture
    add constraint fatture_categoria_not_unclassified_chk
    check (
        categoria is not null
        and btrim(categoria) <> ''
        and upper(btrim(categoria)) <> 'DA CLASSIFICARE'
    );
