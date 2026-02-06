"""Tests for processors/transformers.py — all processor and helper functions."""

import pytest

from processors.transformers import (
    flatten_attack_user,
    flatten_created_by,
    process_payloads,
    process_repeat_offenders,
    process_simulation_user_coverage,
    process_simulation_user_events,
    process_simulation_users,
    process_simulations,
    process_training_user_coverage,
    process_trainings,
    process_users,
)


SNAPSHOT = "2024-06-20"


# ===================================================================
# flatten_attack_user
# ===================================================================

class TestFlattenAttackUser:

    def test_full_data(self):
        user = {"userId": "u1", "displayName": "Alice", "email": "a@contoso.com"}
        result = flatten_attack_user(user)
        assert result == {"userId": "u1", "displayName": "Alice", "email": "a@contoso.com"}

    def test_partial_data(self):
        user = {"userId": "u2"}
        result = flatten_attack_user(user)
        assert result["userId"] == "u2"
        assert result["displayName"] is None
        assert result["email"] is None

    def test_none_input(self):
        result = flatten_attack_user(None)
        assert result == {"userId": None, "displayName": None, "email": None}

    def test_empty_dict(self):
        result = flatten_attack_user({})
        assert result == {"userId": None, "displayName": None, "email": None}


# ===================================================================
# flatten_created_by
# ===================================================================

class TestFlattenCreatedBy:

    def test_full_data_default_prefix(self):
        obj = {"id": "admin-1", "displayName": "Admin", "email": "admin@contoso.com"}
        result = flatten_created_by(obj)
        assert result == {
            "createdById": "admin-1",
            "createdByDisplayName": "Admin",
            "createdByEmail": "admin@contoso.com",
        }

    def test_custom_prefix(self):
        obj = {"id": "mod-1", "displayName": "Mod", "email": "mod@contoso.com"}
        result = flatten_created_by(obj, prefix="lastModifiedBy")
        assert "lastModifiedById" in result
        assert result["lastModifiedById"] == "mod-1"
        assert "lastModifiedByDisplayName" in result
        assert "lastModifiedByEmail" in result

    def test_none_input(self):
        result = flatten_created_by(None)
        assert result == {
            "createdById": None,
            "createdByDisplayName": None,
            "createdByEmail": None,
        }

    def test_empty_dict(self):
        result = flatten_created_by({})
        assert result["createdById"] is None


# ===================================================================
# process_repeat_offenders
# ===================================================================

class TestProcessRepeatOffenders:

    def test_with_sample_data(self, sample_repeat_offender_record, snapshot_date):
        result = process_repeat_offenders([sample_repeat_offender_record], snapshot_date)
        assert len(result) == 1
        row = result[0]
        assert row["snapshotDateUtc"] == snapshot_date
        assert row["userId"] == "user-001"
        assert row["displayName"] == "Alice Smith"
        assert row["email"] == "alice@contoso.com"
        assert row["repeatOffenceCount"] == 3

    def test_empty_list(self, snapshot_date):
        assert process_repeat_offenders([], snapshot_date) == []

    def test_preserves_snapshot_date(self, sample_repeat_offender_record):
        result = process_repeat_offenders([sample_repeat_offender_record], "2099-12-31")
        assert result[0]["snapshotDateUtc"] == "2099-12-31"

    def test_missing_user_field(self, snapshot_date):
        record = {"repeatOffenceCount": 1}
        result = process_repeat_offenders([record], snapshot_date)
        assert result[0]["userId"] is None
        assert result[0]["repeatOffenceCount"] == 1

    def test_multiple_records(self, snapshot_date):
        records = [
            {"attackSimulationUser": {"userId": f"u{i}"}, "repeatOffenceCount": i}
            for i in range(5)
        ]
        result = process_repeat_offenders(records, snapshot_date)
        assert len(result) == 5


# ===================================================================
# process_simulation_user_coverage
# ===================================================================

class TestProcessSimulationUserCoverage:

    def test_with_sample_data(self, sample_simulation_user_coverage_record, snapshot_date):
        result = process_simulation_user_coverage(
            [sample_simulation_user_coverage_record], snapshot_date
        )
        assert len(result) == 1
        row = result[0]
        assert row["userId"] == "user-002"
        assert row["simulationCount"] == 5
        assert row["clickCount"] == 2
        assert row["compromisedCount"] == 1
        assert row["latestSimulationDateTime"] == "2024-06-15T10:30:00Z"

    def test_empty_list(self, snapshot_date):
        assert process_simulation_user_coverage([], snapshot_date) == []

    def test_preserves_snapshot_date(self, sample_simulation_user_coverage_record):
        result = process_simulation_user_coverage(
            [sample_simulation_user_coverage_record], "2025-01-01"
        )
        assert result[0]["snapshotDateUtc"] == "2025-01-01"


# ===================================================================
# process_training_user_coverage
# ===================================================================

class TestProcessTrainingUserCoverage:

    def test_counts_training_statuses(self, sample_training_user_coverage_record, snapshot_date):
        result = process_training_user_coverage(
            [sample_training_user_coverage_record], snapshot_date
        )
        assert len(result) == 1
        row = result[0]
        assert row["assignedTrainingsCount"] == 4
        assert row["completedTrainingsCount"] == 1
        assert row["inProgressTrainingsCount"] == 1
        # notStarted + assigned both count as not started
        assert row["notStartedTrainingsCount"] == 2

    def test_empty_trainings_array(self, snapshot_date):
        record = {
            "attackSimulationUser": {"userId": "u1"},
            "userTrainings": [],
        }
        result = process_training_user_coverage([record], snapshot_date)
        assert result[0]["assignedTrainingsCount"] == 0
        assert result[0]["completedTrainingsCount"] == 0

    def test_missing_user_trainings_key(self, snapshot_date):
        record = {"attackSimulationUser": {"userId": "u1"}}
        result = process_training_user_coverage([record], snapshot_date)
        assert result[0]["assignedTrainingsCount"] == 0

    def test_empty_list(self, snapshot_date):
        assert process_training_user_coverage([], snapshot_date) == []

    def test_preserves_snapshot_date(self, sample_training_user_coverage_record):
        result = process_training_user_coverage(
            [sample_training_user_coverage_record], "2030-01-01"
        )
        assert result[0]["snapshotDateUtc"] == "2030-01-01"


# ===================================================================
# process_simulations
# ===================================================================

class TestProcessSimulations:

    def test_full_record(self, sample_simulation_record, snapshot_date):
        result = process_simulations([sample_simulation_record], snapshot_date)
        assert len(result) == 1
        row = result[0]
        assert row["simulationId"] == "sim-001"
        assert row["displayName"] == "Phishing Campaign Q2"
        assert row["status"] == "completed"
        assert row["attackType"] == "phishing"
        assert row["isAutomated"] is False
        assert row["durationInDays"] == 30
        # Payload
        assert row["payloadId"] == "payload-001"
        assert row["payloadDisplayName"] == "Credential Harvest Payload"
        # Report
        assert row["reportTotalUserCount"] == 100
        assert row["reportCompromisedCount"] == 10
        assert row["reportClickCount"] == 25
        assert row["reportReportedCount"] == 5
        # Created by / modified by
        assert row["createdById"] == "admin-001"
        assert row["lastModifiedById"] == "admin-002"

    def test_no_payload(self, snapshot_date):
        record = {"id": "sim-no-payload", "status": "draft"}
        result = process_simulations([record], snapshot_date)
        assert result[0]["payloadId"] is None
        assert result[0]["payloadDisplayName"] is None

    def test_no_report(self, snapshot_date):
        record = {"id": "sim-no-report", "status": "draft"}
        result = process_simulations([record], snapshot_date)
        assert result[0]["reportTotalUserCount"] is None

    def test_empty_list(self, snapshot_date):
        assert process_simulations([], snapshot_date) == []

    def test_preserves_snapshot_date(self, sample_simulation_record):
        result = process_simulations([sample_simulation_record], "2099-12-31")
        assert result[0]["snapshotDateUtc"] == "2099-12-31"


# ===================================================================
# process_simulation_users
# ===================================================================

class TestProcessSimulationUsers:

    def test_with_sample_data(self, sample_simulation_user_record, snapshot_date):
        result = process_simulation_users(
            [sample_simulation_user_record], snapshot_date, simulation_id="sim-001"
        )
        assert len(result) == 1
        row = result[0]
        assert row["simulationId"] == "sim-001"
        assert row["userId"] == "user-010"
        assert row["email"] == "user10@contoso.com"
        assert row["isCompromised"] is True
        assert row["assignedTrainingsCount"] == 2

    def test_simulation_id_from_record(self, snapshot_date):
        record = {
            "simulationId": "sim-from-record",
            "simulationUser": {"userId": "u1"},
        }
        result = process_simulation_users([record], snapshot_date)
        assert result[0]["simulationId"] == "sim-from-record"

    def test_none_simulation_user(self, snapshot_date):
        record = {"simulationUser": None, "isCompromised": False}
        result = process_simulation_users([record], snapshot_date)
        assert result[0]["userId"] is None

    def test_empty_list(self, snapshot_date):
        assert process_simulation_users([], snapshot_date) == []

    def test_preserves_snapshot_date(self, sample_simulation_user_record):
        result = process_simulation_users(
            [sample_simulation_user_record], "2099-01-01", simulation_id="s1"
        )
        assert result[0]["snapshotDateUtc"] == "2099-01-01"


# ===================================================================
# process_simulation_user_events
# ===================================================================

class TestProcessSimulationUserEvents:

    def test_explodes_events(self, sample_simulation_user_record, snapshot_date):
        result = process_simulation_user_events(
            [sample_simulation_user_record], snapshot_date, simulation_id="sim-001"
        )
        assert len(result) == 2
        assert result[0]["eventName"] == "emailLinkClicked"
        assert result[1]["eventName"] == "credentialSubmitted"
        assert result[0]["userId"] == "user-010"
        assert result[0]["simulationId"] == "sim-001"

    def test_no_events(self, snapshot_date):
        record = {
            "simulationUser": {"userId": "u1"},
            "simulationEvents": [],
        }
        result = process_simulation_user_events([record], snapshot_date)
        assert result == []

    def test_none_events(self, snapshot_date):
        record = {
            "simulationUser": {"userId": "u1"},
            "simulationEvents": None,
        }
        result = process_simulation_user_events([record], snapshot_date)
        assert result == []

    def test_empty_list(self, snapshot_date):
        assert process_simulation_user_events([], snapshot_date) == []

    def test_preserves_snapshot_date(self, sample_simulation_user_record):
        result = process_simulation_user_events(
            [sample_simulation_user_record], "2099-01-01", simulation_id="s1"
        )
        for row in result:
            assert row["snapshotDateUtc"] == "2099-01-01"

    def test_event_fields(self, sample_simulation_user_record, snapshot_date):
        result = process_simulation_user_events(
            [sample_simulation_user_record], snapshot_date, simulation_id="sim-001"
        )
        event = result[0]
        assert event["browser"] == "Chrome"
        assert event["ipAddress"] == "10.0.0.1"
        assert event["osPlatformDeviceDetails"] == "Windows 11"


# ===================================================================
# process_trainings
# ===================================================================

class TestProcessTrainings:

    def test_with_sample_data(self, sample_training_record, snapshot_date):
        result = process_trainings([sample_training_record], snapshot_date)
        assert len(result) == 1
        row = result[0]
        assert row["trainingId"] == "training-001"
        assert row["displayName"] == "Phishing Awareness 101"
        assert row["durationInMinutes"] == 30
        assert row["hasEvaluation"] is True
        assert row["createdById"] == "admin-001"
        # lastModifiedBy is None → should have None values
        assert row["lastModifiedById"] is None

    def test_empty_list(self, snapshot_date):
        assert process_trainings([], snapshot_date) == []

    def test_preserves_snapshot_date(self, sample_training_record):
        result = process_trainings([sample_training_record], "2099-06-01")
        assert result[0]["snapshotDateUtc"] == "2099-06-01"


# ===================================================================
# process_payloads
# ===================================================================

class TestProcessPayloads:

    def test_with_sample_data(self, sample_payload_record, snapshot_date):
        result = process_payloads([sample_payload_record], snapshot_date)
        assert len(result) == 1
        row = result[0]
        assert row["payloadId"] == "payload-001"
        assert row["displayName"] == "Credential Harvest Payload"
        assert row["simulationAttackType"] == "credentialHarvest"
        assert row["platform"] == "email"
        assert row["predictedCompromiseRate"] == 0.15
        assert row["isCurrentEvent"] is False
        assert row["createdById"] == "admin-001"

    def test_none_optional_fields(self, snapshot_date):
        record = {"id": "p1"}
        result = process_payloads([record], snapshot_date)
        row = result[0]
        assert row["simulationAttackType"] is None
        assert row["platform"] is None

    def test_empty_list(self, snapshot_date):
        assert process_payloads([], snapshot_date) == []

    def test_preserves_snapshot_date(self, sample_payload_record):
        result = process_payloads([sample_payload_record], "2099-12-31")
        assert result[0]["snapshotDateUtc"] == "2099-12-31"


# ===================================================================
# process_users
# ===================================================================

class TestProcessUsers:

    def test_with_sample_data(self, sample_user_record, snapshot_date):
        result = process_users([sample_user_record], snapshot_date)
        assert len(result) == 1
        row = result[0]
        assert row["userId"] == "user-010"
        assert row["displayName"] == "User Ten"
        assert row["department"] == "Engineering"
        assert row["accountEnabled"] is True

    def test_empty_list(self, snapshot_date):
        assert process_users([], snapshot_date) == []

    def test_missing_fields_return_none(self, snapshot_date):
        record = {"id": "u1"}
        result = process_users([record], snapshot_date)
        row = result[0]
        assert row["userId"] == "u1"
        assert row["department"] is None
        assert row["jobTitle"] is None

    def test_preserves_snapshot_date(self, sample_user_record):
        result = process_users([sample_user_record], "2099-01-01")
        assert result[0]["snapshotDateUtc"] == "2099-01-01"


# ===================================================================
# Cross-cutting: all processors handle empty input
# ===================================================================

class TestAllProcessorsEmptyInput:
    """Every processor must return [] when given an empty list."""

    @pytest.mark.parametrize(
        "processor",
        [
            process_repeat_offenders,
            process_simulation_user_coverage,
            process_training_user_coverage,
            process_simulations,
            process_trainings,
            process_payloads,
            process_users,
        ],
    )
    def test_empty_input_returns_empty(self, processor, snapshot_date):
        assert processor([], snapshot_date) == []

    def test_simulation_users_empty(self, snapshot_date):
        assert process_simulation_users([], snapshot_date) == []

    def test_simulation_user_events_empty(self, snapshot_date):
        assert process_simulation_user_events([], snapshot_date) == []
