"""Data transformation processors for Graph API responses.

Each processor function transforms raw Graph API response records into
flat dictionaries optimized for Parquet/Power BI consumption.
"""

import logging
from typing import Any, Dict, List, Optional

from utils.security import sanitize_string

logger = logging.getLogger(__name__)


def flatten_attack_user(user_detail: Optional[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    """Flatten attackSimulationUser nested structure with input sanitization.

    Args:
        user_detail: Nested user object from Graph API response

    Returns:
        Flattened dictionary with userId, displayName, email keys
    """
    if not user_detail:
        return {"userId": None, "displayName": None, "email": None}
    return {
        "userId": sanitize_string(user_detail.get("userId")),
        "displayName": sanitize_string(user_detail.get("displayName")),
        "email": sanitize_string(user_detail.get("email")),
    }


def flatten_created_by(obj: Optional[Dict[str, Any]], prefix: str = "createdBy") -> Dict[str, Optional[str]]:
    """Flatten createdBy/lastModifiedBy nested objects.

    Args:
        obj: Nested createdBy or lastModifiedBy object
        prefix: Key prefix for the flattened fields

    Returns:
        Flattened dictionary with {prefix}Id, {prefix}DisplayName, {prefix}Email
    """
    if not obj:
        return {
            f"{prefix}Id": None,
            f"{prefix}DisplayName": None,
            f"{prefix}Email": None,
        }
    return {
        f"{prefix}Id": sanitize_string(obj.get("id")),
        f"{prefix}DisplayName": sanitize_string(obj.get("displayName")),
        f"{prefix}Email": sanitize_string(obj.get("email")),
    }


# ============================================================================
# EXISTING Processors (v1.0 reporting endpoints)
# ============================================================================

def process_repeat_offenders(records: List[Dict[str, Any]], snapshot_date: str) -> List[Dict[str, Any]]:
    """Process repeat offenders data from Graph API."""
    processed: List[Dict[str, Any]] = []
    for record in records:
        user = flatten_attack_user(record.get("attackSimulationUser", {}))
        processed.append({
            "snapshotDateUtc": snapshot_date,
            "userId": user.get("userId"),
            "displayName": user.get("displayName"),
            "email": user.get("email"),
            "repeatOffenceCount": record.get("repeatOffenceCount"),
        })
    return processed


def process_simulation_user_coverage(records: List[Dict[str, Any]], snapshot_date: str) -> List[Dict[str, Any]]:
    """Process simulation user coverage data from Graph API."""
    processed: List[Dict[str, Any]] = []
    for record in records:
        user = flatten_attack_user(record.get("attackSimulationUser", {}))
        processed.append({
            "snapshotDateUtc": snapshot_date,
            "userId": user.get("userId"),
            "displayName": user.get("displayName"),
            "email": user.get("email"),
            "simulationCount": record.get("simulationCount"),
            "latestSimulationDateTime": record.get("latestSimulationDateTime"),
            "clickCount": record.get("clickCount"),
            "compromisedCount": record.get("compromisedCount"),
        })
    return processed


def process_training_user_coverage(records: List[Dict[str, Any]], snapshot_date: str) -> List[Dict[str, Any]]:
    """Process training user coverage data from Graph API.

    The Graph API returns userTrainings as an array of training objects with status.
    This function aggregates them into counts per user.
    """
    processed: List[Dict[str, Any]] = []
    for record in records:
        user = flatten_attack_user(record.get("attackSimulationUser", {}))
        trainings = record.get("userTrainings", [])

        assigned_count = len(trainings)
        completed_count = sum(1 for t in trainings if t.get("trainingStatus") == "completed")
        in_progress_count = sum(1 for t in trainings if t.get("trainingStatus") == "inProgress")
        not_started_count = sum(1 for t in trainings if t.get("trainingStatus") in ("notStarted", "assigned"))

        processed.append({
            "snapshotDateUtc": snapshot_date,
            "userId": user.get("userId"),
            "displayName": user.get("displayName"),
            "email": user.get("email"),
            "assignedTrainingsCount": assigned_count,
            "completedTrainingsCount": completed_count,
            "inProgressTrainingsCount": in_progress_count,
            "notStartedTrainingsCount": not_started_count,
        })
    return processed


def _get_simulation_event_count(events: List[Dict[str, Any]], event_name: str) -> Optional[int]:
    """Extract a count from the simulationEventsContent events array by event name."""
    for event in events:
        if event.get("eventName") == event_name:
            return event.get("count")
    return None


def process_simulations(records: List[Dict[str, Any]], snapshot_date: str) -> List[Dict[str, Any]]:
    """Process simulation data from Graph API."""
    processed: List[Dict[str, Any]] = []
    for record in records:
        created_by = flatten_created_by(record.get("createdBy"), "createdBy")
        last_modified_by = flatten_created_by(record.get("lastModifiedBy"), "lastModifiedBy")
        overview = record.get("report", {}).get("overview", {}) or {}
        sim_events = overview.get("simulationEventsContent", {}) or {}
        events = sim_events.get("events", []) or []
        processed.append({
            "snapshotDateUtc": snapshot_date,
            "simulationId": sanitize_string(record.get("id")),
            "displayName": sanitize_string(record.get("displayName")),
            "description": sanitize_string(record.get("description"), max_length=2000),
            "status": sanitize_string(record.get("status")),
            "attackType": sanitize_string(record.get("attackType")),
            "attackTechnique": sanitize_string(record.get("attackTechnique")),
            "createdDateTime": record.get("createdDateTime"),
            "launchDateTime": record.get("launchDateTime"),
            "completionDateTime": record.get("completionDateTime"),
            "lastModifiedDateTime": record.get("lastModifiedDateTime"),
            "isAutomated": record.get("isAutomated"),
            "automationId": sanitize_string(record.get("automationId")),
            "durationInDays": record.get("durationInDays"),
            "payloadId": record.get("payload", {}).get("id") if record.get("payload") else None,
            "payloadDisplayName": sanitize_string(record.get("payload", {}).get("displayName")) if record.get("payload") else None,
            "reportTotalUserCount": overview.get("resolvedTargetsCount"),
            "reportCompromisedCount": _get_simulation_event_count(events, "CredentialHarvested"),
            "reportClickCount": _get_simulation_event_count(events, "EmailLinkClicked"),
            "reportReportedCount": _get_simulation_event_count(events, "ReportedEmail"),
            **created_by,
            **last_modified_by,
        })
    return processed


# ============================================================================
# Extended processors (beta endpoints)
# ============================================================================

def process_simulation_users(records: List[Dict[str, Any]], snapshot_date: str, simulation_id: str = "") -> List[Dict[str, Any]]:
    """Process simulation user details from beta API.
    
    Endpoint: /beta/security/attackSimulation/simulations/{id}/report/simulationUsers
    Each record is a UserSimulationDetails object.
    """
    processed: List[Dict[str, Any]] = []
    for record in records:
        sim_user = record.get("simulationUser", {}) or {}
        processed.append({
            "snapshotDateUtc": snapshot_date,
            "simulationId": simulation_id or sanitize_string(record.get("simulationId")),
            "userId": sanitize_string(sim_user.get("userId")),
            "email": sanitize_string(sim_user.get("email")),
            "displayName": sanitize_string(sim_user.get("displayName")),
            "compromisedDateTime": record.get("compromisedDateTime"),
            "reportedPhishDateTime": record.get("reportedPhishDateTime"),
            "assignedTrainingsCount": record.get("assignedTrainingsCount"),
            "completedTrainingsCount": record.get("completedTrainingsCount"),
            "inProgressTrainingsCount": record.get("inProgressTrainingsCount"),
            "isCompromised": record.get("isCompromised"),
        })
    return processed


def process_simulation_user_events(records: List[Dict[str, Any]], snapshot_date: str, simulation_id: str = "") -> List[Dict[str, Any]]:
    """Extract simulation events from simulationUsers response.

    Each simulationUser record has a 'simulationEvents' array.
    This explodes those into individual event rows.
    """
    processed: List[Dict[str, Any]] = []
    for record in records:
        sim_user = record.get("simulationUser", {}) or {}
        user_id = sanitize_string(sim_user.get("userId"))
        sim_id = simulation_id or sanitize_string(record.get("simulationId"))
        events = record.get("simulationEvents", []) or []

        for event in events:
            processed.append({
                "snapshotDateUtc": snapshot_date,
                "simulationId": sim_id,
                "userId": user_id,
                "eventName": sanitize_string(event.get("eventName")),
                "eventDateTime": event.get("eventDateTime"),
                "browser": sanitize_string(event.get("browser")),
                "ipAddress": sanitize_string(event.get("ipAddress")),
                "osPlatformDeviceDetails": sanitize_string(event.get("osPlatformDeviceDetails")),
            })
    return processed


def process_trainings(records: List[Dict[str, Any]], snapshot_date: str) -> List[Dict[str, Any]]:
    """Process training definitions from beta API.

    Endpoint: /beta/security/attackSimulation/trainings
    """
    processed: List[Dict[str, Any]] = []
    for record in records:
        created_by = flatten_created_by(record.get("createdBy"), "createdBy")
        last_modified_by = flatten_created_by(record.get("lastModifiedBy"), "lastModifiedBy")
        processed.append({
            "snapshotDateUtc": snapshot_date,
            "trainingId": sanitize_string(record.get("id")),
            "displayName": sanitize_string(record.get("displayName")),
            "description": sanitize_string(record.get("description"), max_length=2000),
            "durationInMinutes": record.get("durationInMinutes"),
            "source": sanitize_string(record.get("source")),
            "type": sanitize_string(str(record.get("type"))) if record.get("type") else None,
            "availabilityStatus": sanitize_string(str(record.get("availabilityStatus"))) if record.get("availabilityStatus") else None,
            "hasEvaluation": record.get("hasEvaluation"),
            "lastModifiedDateTime": record.get("lastModifiedDateTime"),
            **created_by,
            **last_modified_by,
        })
    return processed


def process_payloads(records: List[Dict[str, Any]], snapshot_date: str) -> List[Dict[str, Any]]:
    """Process payload data from beta API.

    Endpoint: /beta/security/attackSimulation/payloads?$filter=source eq 'tenant'
    Graph API returns ``name`` (not ``displayName``), ``Brand`` (capital B),
    and ``payloadIndustry`` (not ``industry``).
    """
    processed: List[Dict[str, Any]] = []
    for record in records:
        created_by = flatten_created_by(record.get("createdBy"), "createdBy")
        last_modified_by = flatten_created_by(record.get("lastModifiedBy"), "lastModifiedBy")
        # Graph API uses "name" for payloads, not "displayName"
        display_name = record.get("displayName") or record.get("name")
        processed.append({
            "snapshotDateUtc": snapshot_date,
            "payloadId": sanitize_string(record.get("id")),
            "displayName": sanitize_string(display_name),
            "description": sanitize_string(record.get("description"), max_length=2000),
            "simulationAttackType": sanitize_string(str(record.get("simulationAttackType"))) if record.get("simulationAttackType") else None,
            "platform": sanitize_string(str(record.get("platform"))) if record.get("platform") else None,
            "status": sanitize_string(str(record.get("status"))) if record.get("status") else None,
            "source": sanitize_string(str(record.get("source"))) if record.get("source") else None,
            "predictedCompromiseRate": record.get("predictedCompromiseRate"),
            "complexity": sanitize_string(str(record.get("complexity"))) if record.get("complexity") else None,
            "technique": sanitize_string(str(record.get("technique"))) if record.get("technique") else None,
            "theme": sanitize_string(str(record.get("theme"))) if record.get("theme") else None,
            "brand": sanitize_string(str(record.get("Brand") or record.get("brand"))) if (record.get("Brand") or record.get("brand")) else None,
            "industry": sanitize_string(str(record.get("payloadIndustry") or record.get("industry"))) if (record.get("payloadIndustry") or record.get("industry")) else None,
            "isCurrentEvent": record.get("isCurrentEvent"),
            "isControversial": record.get("isControversial"),
            "lastModifiedDateTime": record.get("lastModifiedDateTime"),
            **created_by,
            **last_modified_by,
        })
    return processed


def process_users(records: List[Dict[str, Any]], snapshot_date: str) -> List[Dict[str, Any]]:
    """Process Entra ID user details.

    Endpoint: /v1.0/users/{id} or /v1.0/users?$filter=id in (...)
    Used for enriching simulation user data with org details.
    """
    processed: List[Dict[str, Any]] = []
    for record in records:
        processed.append({
            "snapshotDateUtc": snapshot_date,
            "userId": sanitize_string(record.get("id")),
            "displayName": sanitize_string(record.get("displayName")),
            "givenName": sanitize_string(record.get("givenName")),
            "surname": sanitize_string(record.get("surname")),
            "mail": sanitize_string(record.get("mail")),
            "department": sanitize_string(record.get("department")),
            "companyName": sanitize_string(record.get("companyName")),
            "city": sanitize_string(record.get("city")),
            "country": sanitize_string(record.get("country")),
            "jobTitle": sanitize_string(record.get("jobTitle")),
            "accountEnabled": record.get("accountEnabled"),
        })
    return processed
