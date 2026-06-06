"""Router FastAPI per dominio.

Estratti progressivamente da services/fastapi_worker.py (god file) per
migliorarne la manutenibilità. Ogni router usa gli stessi helper condivisi
(_verify_worker_key, _resolve_user_from_token, _get_supabase_client,
_resolve_ristorante_id) importandoli dal worker, e viene montato con
app.include_router() in fondo a fastapi_worker.py — così il comportamento HTTP
(path, gate, response) resta identico.
"""
