-- Difesa in profondità per il CRITICAL trovato dall'audit Security 29/7:
-- _quote_percentuali (services/routers/riparto.py) accettava un ristorante_id
-- dal body HTTP senza verificarne l'ownership, scrivendo su
-- riparto_costi_catena_quote.ristorante_id senza alcun vincolo referenziale.
-- Il fix applicativo è già in produzione (validazione contro le sedi del
-- chiamante); questa FK impedisce a livello DB che una riga punti a un
-- ristorante_id inesistente, qualunque sia il percorso di scrittura.
-- Verificato in precedenza: nessuna riga orfana nel DB live.

ALTER TABLE riparto_costi_catena_quote
  ADD CONSTRAINT riparto_costi_catena_quote_ristorante_id_fkey
  FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id);
