import pytest

from notification.domain.provider_template import matches


def test_approved_body_matches_text_and_parameter_positions():
    assert matches(
        "Hello {{ name }}",
        {"template_parameters": ["name"]},
        [{"type": "BODY", "text": "Hello {{1}}"}],
    )
    assert matches("Static body", None, [{"type": "BODY", "text": "Static body"}])
    payload = {
        "components": [
            {"type": "header", "parameters": [{"type": "text", "variable": "name"}]},
            {"type": "body", "parameters": [{"type": "text", "variable": "amount"}]},
            {
                "type": "button",
                "sub_type": "url",
                "index": "0",
                "parameters": [{"type": "text", "variable": "link"}],
            },
        ]
    }
    assert matches(
        "Pay {{amount}}",
        payload,
        [
            {"type": "HEADER", "format": "TEXT", "text": "Hi {{1}}"},
            {"type": "BODY", "text": "Pay {{1}}"},
            {
                "type": "BUTTONS",
                "buttons": [{"type": "URL", "url": "https://example.invalid/{{1}}"}],
            },
        ],
    )


@pytest.mark.parametrize(
    "remote",
    [
        None,
        [1],
        [{"type": "HEADER", "format": "IMAGE"}],
        [{"type": "BODY", "text": []}],
        [{"type": "BODY", "text": "Hi {{name}}"}],
        [{"type": "BODY", "text": "Hi {{0}}"}],
        [{"type": "BODY", "text": "Hi {{2}}"}],
        [{"type": "BODY", "text": "Different body"}],
        [{"type": "BODY", "text": "Hi {{1}}"}],
        [{"type": "BUTTONS", "buttons": {}}],
        [{"type": "BUTTONS", "buttons": [1]}],
        [{"type": "BUTTONS", "buttons": [{"url": []}]}],
        [{"type": "BUTTONS", "buttons": [{"type": "URL", "url": "{{2}}"}]}],
    ],
)
def test_incompatible_approved_templates_fail_closed(remote):
    assert not matches("Static body", None, remote)


def test_undeclared_local_component_is_not_implicitly_approved():
    assert not matches(
        "Static body", {"template_parameters": ["name"]}, [{"type": "BODY", "text": "Static body"}]
    )
    assert not matches(
        "Static body",
        {"components": [{"type": "header", "parameters": [{"variable": "name"}]}]},
        [{"type": "BODY", "text": "Static body"}],
    )
