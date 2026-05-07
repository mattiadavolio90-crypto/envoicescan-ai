"""Test per services/ai_cost_service.py — funzioni pure senza Supabase/Streamlit."""
import pytest
from services.ai_cost_service import (
    calcola_costi_gpt4o_mini,
    GPT4O_MINI_INPUT_PER_M_TOKEN,
    GPT4O_MINI_OUTPUT_PER_M_TOKEN,
)


class TestCalcolaCostiGpt4oMini:
    def test_zero_tokens_returns_zero_costs(self):
        result = calcola_costi_gpt4o_mini(0, 0)
        assert result['total_cost'] == 0.0
        assert result['input_cost'] == 0.0
        assert result['output_cost'] == 0.0
        assert result['total_tokens'] == 0

    def test_returns_correct_keys(self):
        result = calcola_costi_gpt4o_mini(100, 50)
        assert set(result.keys()) == {
            'prompt_tokens', 'completion_tokens', 'total_tokens',
            'input_cost', 'output_cost', 'total_cost',
        }

    def test_token_counts_preserved(self):
        result = calcola_costi_gpt4o_mini(1000, 500)
        assert result['prompt_tokens'] == 1000
        assert result['completion_tokens'] == 500
        assert result['total_tokens'] == 1500

    def test_input_cost_formula(self):
        result = calcola_costi_gpt4o_mini(1_000_000, 0)
        assert abs(result['input_cost'] - GPT4O_MINI_INPUT_PER_M_TOKEN) < 1e-10

    def test_output_cost_formula(self):
        result = calcola_costi_gpt4o_mini(0, 1_000_000)
        assert abs(result['output_cost'] - GPT4O_MINI_OUTPUT_PER_M_TOKEN) < 1e-10

    def test_total_cost_is_sum_of_input_and_output(self):
        result = calcola_costi_gpt4o_mini(300_000, 100_000)
        assert abs(result['total_cost'] - (result['input_cost'] + result['output_cost'])) < 1e-12

    def test_none_tokens_treated_as_zero(self):
        result = calcola_costi_gpt4o_mini(None, None)
        assert result['total_tokens'] == 0
        assert result['total_cost'] == 0.0

    def test_output_is_more_expensive_per_token_than_input(self):
        """Il costo per token di output deve essere maggiore di quello di input."""
        assert GPT4O_MINI_OUTPUT_PER_M_TOKEN > GPT4O_MINI_INPUT_PER_M_TOKEN

    def test_typical_request_cost_in_expected_range(self):
        """500 token input + 200 token output → costo < 0.001 USD."""
        result = calcola_costi_gpt4o_mini(500, 200)
        assert result['total_cost'] < 0.001

    def test_large_batch_cost_plausible(self):
        """100k token input + 50k output → tra 0.01 e 1 USD."""
        result = calcola_costi_gpt4o_mini(100_000, 50_000)
        assert 0.01 < result['total_cost'] < 1.0
