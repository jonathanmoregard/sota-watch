"""Classification of `claude -p --output-format json` stdout.

Payloads below are verbatim (trimmed) captures from
~/.local/share/sota-watch/run.log — the real shapes the runner has seen.
"""
from watch.result import classify

USAGE_LIMIT = (
    '{"type":"result","subtype":"success","is_error":true,"api_error_status":429,'
    '"duration_ms":589,"num_turns":1,'
    '"result":"You\'ve hit your org\'s monthly usage limit",'
    '"session_id":"5d5593cd-b057-4a53-843d-4bc78f718378","total_cost_usd":0}'
)

AUTH_EXPIRED = (
    '{"type":"result","subtype":"success","is_error":true,"api_error_status":401,'
    '"duration_ms":2043,"num_turns":1,'
    '"result":"Failed to authenticate. API Error: 401 OAuth access token has expired. '
    'Re-authenticate to continue.","session_id":"59e033bf","total_cost_usd":0}'
)

NOT_LOGGED_IN = (
    '{"type":"result","subtype":"success","is_error":true,"api_error_status":null,'
    '"duration_ms":21,"num_turns":1,"result":"Not logged in · Please run /login",'
    '"session_id":"eb428091","total_cost_usd":0}'
)

SUCCESS = (
    '{"type":"result","subtype":"success","is_error":false,"api_error_status":null,'
    '"duration_ms":74000,"num_turns":14,"result":"Run complete.",'
    '"session_id":"6904c015","total_cost_usd":0.57}'
)


def test_usage_limit_is_retryable_on_another_model():
    assert classify(USAGE_LIMIT) == "usage_limit"


def test_five_hour_limit_wording_also_counts():
    assert classify(
        '{"type":"result","is_error":true,"api_error_status":429,'
        '"result":"Claude usage limit reached. Your limit will reset at 3pm."}'
    ) == "usage_limit"


def test_auth_failure_is_not_a_usage_limit():
    """Switching model cannot fix expired OAuth — must not burn a fallback attempt."""
    assert classify(AUTH_EXPIRED) == "error"
    assert classify(NOT_LOGGED_IN) == "error"


def test_success():
    assert classify(SUCCESS) == "ok"


def test_preamble_lines_are_ignored():
    noisy = "some stderr noise\n" + SUCCESS + "\n"
    assert classify(noisy) == "ok"


def test_last_json_line_wins():
    assert classify(SUCCESS + "\n" + USAGE_LIMIT) == "usage_limit"


def test_empty_or_garbage_output_is_error():
    assert classify("") == "error"
    assert classify("claude: command not found") == "error"
    assert classify("{not json}") == "error"
