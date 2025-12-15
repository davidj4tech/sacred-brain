from sacred_brain.routing import determine_route, detect_error_loop, escalate_route


def test_determine_route_defaults_to_fast():
    decision = determine_route("hello world")
    assert decision.alias == "sam-fast"
    assert decision.reason == "default"


def test_determine_route_code_keyword():
    decision = determine_route("Here is a traceback ``` ValueError")
    assert decision.alias == "sam-code"
    assert decision.reason == "code_keyword"


def test_determine_route_vision_keyword():
    decision = determine_route("please describe this image")
    assert decision.alias == "sam-vision"
    assert decision.reason == "vision_keyword"


def test_determine_route_creative_keyword():
    decision = determine_route("write a poem about tea")
    assert decision.alias == "sam-creative"
    assert decision.reason == "creative_keyword"


def test_error_escalation_detects_loop():
    assert detect_error_loop("that didn't work") is True
    decision = determine_route("that didn't work again")
    assert decision.alias == "sam-deep"
    assert decision.reason == "error_escalation"


def test_escalate_route():
    assert escalate_route("sam-fast") == "sam-deep"
    assert escalate_route("sam-code") == "sam-deep"
    assert escalate_route("sam-deep") == "sam-deep"
