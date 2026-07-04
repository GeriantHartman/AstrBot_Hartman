from plugins.astrbot_plugin_agentic_RPG.core.config_switch_registry import (
    build_config_switch_audit_map,
    render_config_switch_report,
)


def _getter(values):
    return lambda key, default=None: values.get(key, default)


def test_config_switch_report_marks_disabled_and_inactive_features():
    config = {
        "enable_character_director": False,
        "enable_life_engine": False,
        "life_engine_auto_seed_commissions": True,
        "disable_chat_template_injection": True,
        "router_supervisor_5_validation_mode": "off",
    }

    report = build_config_switch_audit_map(_getter(config))

    assert report["switches"]["enable_character_director"]["status"] == "disabled"
    assert report["switches"]["disable_chat_template_injection"]["status"] == (
        "disabled"
    )
    assert report["switches"]["router_supervisor_5_validation_mode"]["status"] == (
        "disabled"
    )
    assert report["switches"]["life_engine_auto_seed_commissions"]["status"] == (
        "inactive_dependency"
    )
    assert report["switches"]["life_engine_auto_seed_commissions"]["blocked_by"] == [
        "enable_life_engine"
    ]


def test_render_config_switch_report_supports_single_key_lookup():
    text = render_config_switch_report(
        _getter({"enable_character_director": False}),
        action="enable_character_director",
    )

    assert "Character Director" in text
    assert "已关闭" in text
    assert "关闭/未生效时可跳过" in text
    assert "Director latency" in text


def test_render_config_switch_report_off_view_has_summary():
    text = render_config_switch_report(
        _getter(
            {
                "enable_life_engine": False,
                "disable_chat_template_injection": True,
            }
        ),
        action="off",
    )

    assert "RPG Config 开关映射" in text
    assert "已关闭" in text
    assert "联动未生效" in text
