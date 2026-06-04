"""Tracking centralizzato per costi AI e ledger eventi."""

from __future__ import annotations

from typing import Any

from config.logger_setup import get_logger

logger = get_logger('ai_cost')

GPT4O_MINI_INPUT_PER_M_TOKEN = 0.15
GPT4O_MINI_OUTPUT_PER_M_TOKEN = 0.60

# Tariffe per modello ($/M token). Aggiornare se OpenAI modifica i listini.
_MODEL_TARIFFE: dict[str, tuple[float, float]] = {
    "gpt-4o-mini":  (0.15,  0.60),
    "gpt-4.1-mini": (0.40,  1.60),
    "gpt-4.1":      (2.00,  8.00),
    "gpt-4o":       (2.50, 10.00),
}
_DEFAULT_TARIFFA = (0.15, 0.60)  # fallback su gpt-4o-mini se modello sconosciuto


def calcola_costi_modello(prompt_tokens: int, completion_tokens: int, model: str = "gpt-4o-mini") -> dict[str, float | int]:
    prompt_tokens = int(prompt_tokens or 0)
    completion_tokens = int(completion_tokens or 0)
    in_per_m, out_per_m = _MODEL_TARIFFE.get(model, _DEFAULT_TARIFFA)
    input_cost = (prompt_tokens / 1_000_000) * in_per_m
    output_cost = (completion_tokens / 1_000_000) * out_per_m
    total_cost = input_cost + output_cost
    return {
        'prompt_tokens': prompt_tokens,
        'completion_tokens': completion_tokens,
        'total_tokens': prompt_tokens + completion_tokens,
        'input_cost': input_cost,
        'output_cost': output_cost,
        'total_cost': total_cost,
    }


def calcola_costi_gpt4o_mini(prompt_tokens: int, completion_tokens: int) -> dict[str, float | int]:
    return calcola_costi_modello(prompt_tokens, completion_tokens, model="gpt-4o-mini")


def _get_session_user_id() -> str | None:
    try:
        import streamlit as st
        user_data = st.session_state.get('user_data', {}) or {}
        return user_data.get('id')
    except Exception:
        return None


def get_daily_ai_usage_count(
    *,
    ristorante_id: str | None,
    operation_types: list[str] | tuple[str, ...],
) -> int:
    """Conta gli eventi AI del giorno corrente per un ristorante e uno o più tipi operazione."""
    if not ristorante_id or not operation_types:
        return 0

    try:
        from datetime import datetime, timezone
        from services import get_supabase_client

        supabase = get_supabase_client()
        day_start = datetime.now(timezone.utc).strftime('%Y-%m-%dT00:00:00+00:00')
        normalized_types = [str(op).strip() for op in operation_types if str(op).strip()]
        if not normalized_types:
            return 0

        query = (
            supabase.table('ai_usage_events')
            .select('id', count='exact')
            .eq('ristorante_id', ristorante_id)
            .gte('created_at', day_start)
        )
        if len(normalized_types) == 1:
            query = query.eq('operation_type', normalized_types[0])
        else:
            query = query.in_('operation_type', normalized_types)

        resp = query.execute()
        return int(resp.count or 0)
    except Exception as exc:
        logger.warning('⚠️ Errore conteggio daily AI usage: %s', exc)
        return 0


def get_daily_quota_status(
    *,
    ristorante_id: str | None,
    operation_types: list[str] | tuple[str, ...],
    daily_limit: int,
) -> dict[str, int | bool]:
    """Restituisce stato quota giornaliera per uno o più tipi operazione."""
    used = get_daily_ai_usage_count(
        ristorante_id=ristorante_id,
        operation_types=operation_types,
    )
    limit = max(0, int(daily_limit or 0))
    remaining = max(0, limit - used)
    return {
        'used': used,
        'limit': limit,
        'remaining': remaining,
        'is_exceeded': used >= limit if limit > 0 else False,
    }


def track_ai_usage(
    *,
    operation_type: str,
    prompt_tokens: int,
    completion_tokens: int,
    ristorante_id: str | None,
    user_id: str | None = None,
    model: str = 'gpt-4o-mini',
    source_file: str | None = None,
    item_count: int | None = 1,
    metadata: dict[str, Any] | None = None,
) -> dict[str, float | int] | None:
    """Traccia un evento AI in ledger e, in fallback, sui contatori legacy."""
    cost_data = calcola_costi_modello(prompt_tokens, completion_tokens, model=model)

    if not ristorante_id:
        logger.warning(
            "⚠️ AI Cost NON tracked: ristorante_id mancante. Costo: $%.6f (%s tokens)",
            cost_data['total_cost'],
            cost_data['total_tokens'],
        )
        return cost_data

    if not user_id:
        user_id = _get_session_user_id()

    try:
        from services import get_supabase_client

        supabase = get_supabase_client()
        payload = {
            'p_ristorante_id': ristorante_id,
            'p_operation_type': operation_type,
            'p_model': model,
            'p_prompt_tokens': cost_data['prompt_tokens'],
            'p_completion_tokens': cost_data['completion_tokens'],
            'p_input_cost': float(cost_data['input_cost']),
            'p_output_cost': float(cost_data['output_cost']),
            'p_total_cost': float(cost_data['total_cost']),
            'p_user_id': user_id,
            'p_source_file': source_file,
            'p_item_count': int(item_count or 1),
            'p_metadata': metadata or {},
        }
        supabase.rpc('track_ai_usage_event', payload).execute()
        logger.info(
            "💰 AI usage tracked: type=%s cost=$%.6f tokens=%s ristorante=%s",
            operation_type,
            cost_data['total_cost'],
            cost_data['total_tokens'],
            ristorante_id,
        )
    except Exception as track_err:
        logger.warning("⚠️ Errore tracking ledger AI, fallback legacy con retry: %s", track_err)
        # Retry esponenziale per garantire tracking costi anche su transient failures
        import time as _time
        _legacy_payload = {
            'p_ristorante_id': ristorante_id,
            'p_cost': float(cost_data['total_cost']),
            'p_tokens': int(cost_data['total_tokens']),
            'p_operation_type': operation_type,
        }
        _tracked = False
        for _attempt in range(3):
            try:
                from services import get_supabase_client
                supabase = get_supabase_client()
                supabase.rpc('increment_ai_cost', _legacy_payload).execute()
                _tracked = True
                break
            except Exception as legacy_err:
                if _attempt < 2:
                    _time.sleep(2 ** _attempt)  # 1s, 2s
                    continue
                logger.critical(
                    "❌ AI cost NON tracciato dopo 3 retry: %s | costo=$%.6f tokens=%s op=%s ristorante=%s",
                    legacy_err,
                    cost_data['total_cost'],
                    cost_data['total_tokens'],
                    operation_type,
                    ristorante_id,
                )

    return cost_data


# === [M7] Alert soglia costi AI mensile ===
import os as _os_ai_cost

AI_MONTHLY_COST_THRESHOLD_USD = float(_os_ai_cost.environ.get('AI_MONTHLY_COST_THRESHOLD_USD', '10.0'))


def get_monthly_ai_cost(
    ristorante_id: str,
    year: int | None = None,
    month: int | None = None,
    supabase_client=None,
) -> dict[str, float | int]:
    """Somma costi e token AI del mese indicato (default: mese corrente).

    Ritorna {'total_cost': float, 'total_tokens': int, 'event_count': int}.
    """
    from datetime import datetime, timezone

    if not ristorante_id:
        return {'total_cost': 0.0, 'total_tokens': 0, 'event_count': 0}

    now = datetime.now(timezone.utc)
    _y = int(year) if year else now.year
    _m = int(month) if month else now.month
    _start = datetime(_y, _m, 1, tzinfo=timezone.utc).isoformat()
    if _m == 12:
        _end = datetime(_y + 1, 1, 1, tzinfo=timezone.utc).isoformat()
    else:
        _end = datetime(_y, _m + 1, 1, tzinfo=timezone.utc).isoformat()

    try:
        if supabase_client is None:
            from services import get_supabase_client
            supabase_client = get_supabase_client()
        resp = (
            supabase_client.table('ai_usage_events')
            .select('total_cost,total_tokens')
            .eq('ristorante_id', str(ristorante_id))
            .gte('created_at', _start)
            .lt('created_at', _end)
            .limit(100000)
            .execute()
        )
        rows = resp.data or []
        total_cost = sum(float(r.get('total_cost') or 0.0) for r in rows)
        total_tokens = sum(int(r.get('total_tokens') or 0) for r in rows)
        return {
            'total_cost': round(total_cost, 6),
            'total_tokens': total_tokens,
            'event_count': len(rows),
        }
    except Exception as exc:
        logger.warning("⚠️ Errore lettura costi AI mensili: %s", exc)
        return {'total_cost': 0.0, 'total_tokens': 0, 'event_count': 0}


def check_monthly_cost_threshold(
    ristorante_id: str,
    threshold_usd: float | None = None,
    supabase_client=None,
) -> dict[str, float | bool]:
    """Ritorna stato soglia mensile costi AI per il ristorante.

    Output: {'exceeded': bool, 'current_cost': float, 'threshold': float,
             'percentage': float, 'warning': bool (>= 80%)}.
    """
    _threshold = float(threshold_usd if threshold_usd is not None else AI_MONTHLY_COST_THRESHOLD_USD)
    if _threshold <= 0 or not ristorante_id:
        return {
            'exceeded': False,
            'current_cost': 0.0,
            'threshold': _threshold,
            'percentage': 0.0,
            'warning': False,
        }

    usage = get_monthly_ai_cost(ristorante_id, supabase_client=supabase_client)
    _current = float(usage['total_cost'])
    _pct = (_current / _threshold) * 100.0 if _threshold > 0 else 0.0
    return {
        'exceeded': _current >= _threshold,
        'current_cost': round(_current, 4),
        'threshold': _threshold,
        'percentage': round(_pct, 1),
        'warning': _pct >= 80.0,
    }