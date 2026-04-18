"""Tracking centralizzato per costi AI e ledger eventi."""

from __future__ import annotations

from typing import Any

from config.logger_setup import get_logger

logger = get_logger('ai_cost')

GPT4O_MINI_INPUT_PER_M_TOKEN = 0.15
GPT4O_MINI_OUTPUT_PER_M_TOKEN = 0.60


def calcola_costi_gpt4o_mini(prompt_tokens: int, completion_tokens: int) -> dict[str, float | int]:
    prompt_tokens = int(prompt_tokens or 0)
    completion_tokens = int(completion_tokens or 0)
    input_cost = (prompt_tokens / 1_000_000) * GPT4O_MINI_INPUT_PER_M_TOKEN
    output_cost = (completion_tokens / 1_000_000) * GPT4O_MINI_OUTPUT_PER_M_TOKEN
    total_cost = input_cost + output_cost
    return {
        'prompt_tokens': prompt_tokens,
        'completion_tokens': completion_tokens,
        'total_tokens': prompt_tokens + completion_tokens,
        'input_cost': input_cost,
        'output_cost': output_cost,
        'total_cost': total_cost,
    }


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
    cost_data = calcola_costi_gpt4o_mini(prompt_tokens, completion_tokens)

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
        logger.warning("⚠️ Errore tracking ledger AI, fallback legacy: %s", track_err)
        try:
            from services import get_supabase_client

            supabase = get_supabase_client()
            supabase.rpc('increment_ai_cost', {
                'p_ristorante_id': ristorante_id,
                'p_cost': float(cost_data['total_cost']),
                'p_tokens': int(cost_data['total_tokens']),
                'p_operation_type': operation_type,
            }).execute()
        except Exception as legacy_err:
            logger.error(
                "❌ Errore tracking costo AI anche in fallback legacy: %s | costo=$%.6f",
                legacy_err,
                cost_data['total_cost'],
            )

    return cost_data