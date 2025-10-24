"""Tests for configuration validation utilities."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict

sys.path.append(str(Path(__file__).resolve().parents[1]))

from config_validation import validate_configuration


def build_settings(**overrides: Dict[str, object]):
    settings = {
        'call_sign': 'Falcon01',
        'log_retention': 30,
        'font_scale': 100,
        'auto_backup': True,
        'prompt_before_sync': False,
        'modules': {
            'ballistics': True,
            'nav_map': False,
            'game_log': False,
        },
    }
    settings.update(overrides)
    return settings


def validate_single_issue(settings, available_modules, field):
    issues = validate_configuration(settings, available_modules=available_modules)
    assert issues, "Expected at least one validation issue"
    assert issues[0].field == field
    return issues[0]


def test_valid_configuration_passes():
    settings = build_settings()
    issues = validate_configuration(settings, available_modules=settings['modules'].keys())
    assert issues == []


def test_call_sign_required():
    settings = build_settings(call_sign='')
    issue = validate_single_issue(settings, settings['modules'].keys(), 'call_sign')
    assert 'call sign' in issue.message.lower()


def test_call_sign_character_restrictions():
    settings = build_settings(call_sign='Falcon 01')
    issue = validate_single_issue(settings, settings['modules'].keys(), 'call_sign')
    assert 'letters, numbers' in issue.message


def test_log_retention_range_enforced():
    settings = build_settings(log_retention=2)
    issue = validate_single_issue(settings, settings['modules'].keys(), 'log_retention')
    assert 'between 7 and 365' in issue.message


def test_font_scale_range_enforced():
    settings = build_settings(font_scale=200)
    issue = validate_single_issue(settings, settings['modules'].keys(), 'font_scale')
    assert '80% and 140%' in issue.message


def test_at_least_one_module_enabled():
    settings = build_settings(modules={'ballistics': False, 'nav_map': False})
    issue = validate_single_issue(settings, ['ballistics', 'nav_map'], 'modules')
    assert 'at least one module' in issue.message.lower()


def test_prompt_before_sync_requires_auto_backup():
    settings = build_settings(auto_backup=False, prompt_before_sync=True)
    issue = validate_single_issue(settings, settings['modules'].keys(), 'prompt_before_sync')
    assert 'automatic backups' in issue.message

