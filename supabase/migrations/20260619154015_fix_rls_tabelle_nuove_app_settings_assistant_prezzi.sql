-- Hardening RLS per 3 tabelle nuove (advisor ERROR rls_disabled_in_public).
-- Stesso pattern collaudato su sessioni: REVOKE anon/authenticated + ENABLE/FORCE RLS.
-- Sicuro perché l'auth è custom (auth.uid()=NULL) e tutto l'accesso applicativo
-- passa da service_role, che bypassa RLS e grant. Nessun dato/struttura modificata.

-- prezzi_preferiti: user_id + preferenze prezzi per sede (dati cliente)
REVOKE ALL ON TABLE public.prezzi_preferiti FROM anon, authenticated;
ALTER TABLE public.prezzi_preferiti ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.prezzi_preferiti FORCE ROW LEVEL SECURITY;

-- app_settings: config key/value globale
REVOKE ALL ON TABLE public.app_settings FROM anon, authenticated;
ALTER TABLE public.app_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.app_settings FORCE ROW LEVEL SECURITY;

-- assistant_preferences: preferenze assistente AI per sede (nome referente, config)
REVOKE ALL ON TABLE public.assistant_preferences FROM anon, authenticated;
ALTER TABLE public.assistant_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.assistant_preferences FORCE ROW LEVEL SECURITY;
