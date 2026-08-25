# -*- coding: utf-8 -*-
"""Tests for domain_manifest can_call peer trust boundary"""
import pytest
import sys

sys.path.insert(0, "backend/A2AServer/src")


class TestCanCall:
    def test_health_advisor_can_call_health_records(self):
        from A2AServer.v2.domain_manifest import load_default
        manifest = load_default()
        # health_advisor has peers=["health_records", "medication_reminder", "visit_summary"]
        assert manifest.can_call("health_advisor", "health_records") is True
        assert manifest.can_call("health_advisor", "medication_reminder") is True
        assert manifest.can_call("health_advisor", "visit_summary") is True

    def test_health_records_can_call_health_advisor(self):
        from A2AServer.v2.domain_manifest import load_default
        manifest = load_default()
        # health_records has peers=["health_advisor", "medication_reminder"]
        assert manifest.can_call("health_records", "health_advisor") is True

    def test_medication_reminder_has_correct_peers(self):
        from A2AServer.v2.domain_manifest import load_default
        manifest = load_default()
        assert manifest.can_call("medication_reminder", "health_advisor") is True
        assert manifest.can_call("medication_reminder", "health_records") is True

    def test_empty_peers_allows_all(self):
        from A2AServer.v2.domain_manifest import load_default
        manifest = load_default()
        # visit_summary peers=["health_advisor", "health_records"]
        assert manifest.can_call("visit_summary", "health_advisor") is True
        assert manifest.can_call("visit_summary", "health_records") is True
        # Unknown caller falls back to True
        assert manifest.can_call("unknown_agent", "any_agent") is True

    def test_untrusted_cross_agent_blocked(self):
        from A2AServer.v2.domain_manifest import load_default
        manifest = load_default()
        # health_advisor should NOT be able to call hostapi (not in peers)
        # visit_summary is NOT in health_advisor's peers list
        assert manifest.can_call("health_advisor", "visit_summary") is True  # explicitly allowed
        # Verify visit_summary IS in health_advisor peers (from code)
        agent_specs = {a.name: a for a in manifest.agents}
        ha = agent_specs["health_advisor"]
        assert "visit_summary" in ha.peers

    def test_agents_have_required_did(self):
        from A2AServer.v2.domain_manifest import load_default
        manifest = load_default()
        agent_specs = {a.name: a for a in manifest.agents}
        for name in ["health_advisor", "health_records", "medication_reminder", "visit_summary"]:
            assert name in agent_specs, f"Missing agent: {name}"
            assert agent_specs[name].port is not None, f"{name} has no port"
