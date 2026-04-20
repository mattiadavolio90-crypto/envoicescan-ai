-- Ensure RLS and service_role write policy are active for retention status

ALTER TABLE public.system_maintenance_status ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Solo service_role può scrivere retention status"
  ON public.system_maintenance_status
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);
