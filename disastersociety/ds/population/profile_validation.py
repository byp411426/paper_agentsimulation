"""Input consistency checks, independent of resident behavior or outcomes.

Reject contradictory new inputs; never repair frozen profiles in place.
"""

from __future__ import annotations


# 2018 ACS PUMS HHT: categories 4/6 live alone; 5/7 do not.
HHT_STRUCTURE = {
    1: "married_couple", 2: "other_male_householder", 3: "other_female_householder",
    4: "nonfamily_living_alone", 5: "nonfamily_not_living_alone",
    6: "nonfamily_living_alone", 7: "nonfamily_not_living_alone",
}


def validate_household_structure(household_id, structure, member_count):
    if member_count < 1:
        raise ValueError(f"{household_id}: household has no members")
    if structure == "nonfamily_living_alone" and member_count != 1:
        raise ValueError(f"{household_id}: living_alone contradicts {member_count} members")
    if structure == "nonfamily_not_living_alone" and member_count < 2:
        raise ValueError(f"{household_id}: not_living_alone contradicts {member_count} members")


def validate_e1_profiles(profiles: list[dict]) -> None:
    """Validate identities, role lists and housing facts before building a run."""
    seen_households, seen_residents = set(), set()
    for profile in profiles:
        hid = profile["household_id"]
        if hid in seen_households:
            raise ValueError(f"duplicate household_id: {hid}")
        seen_households.add(hid)
        members = profile["member_profiles"]
        shared = profile["shared_attributes"]
        validate_household_structure(hid, shared.get("household_structure"), len(members))
        ids, decision_ids, dependent_ids, care_ids = set(), set(), set(), set()
        for member in members:
            rid = member["resident_id"]
            if rid in seen_residents:
                raise ValueError(f"duplicate resident_id: {rid}")
            seen_residents.add(rid)
            ids.add(rid)
            if member.get("household_id", hid) != hid:
                raise ValueError(f"{rid}: household_id disagrees with {hid}")
            capable = member["decision_capable"]
            if not isinstance(capable, bool):
                raise ValueError(f"{rid}: decision_capable must be boolean")
            (decision_ids if capable else dependent_ids).add(rid)
            if member.get("needs_execution_assistance"):
                care_ids.add(rid)
        if not decision_ids:
            raise ValueError(f"{hid}: no decision-capable resident")
        for field, expected in (
            ("decision_resident_ids", decision_ids),
            ("nondecision_member_ids", dependent_ids),
            ("care_recipient_ids", care_ids),
        ):
            if field in profile:
                actual = profile[field]
                if len(actual) != len(set(actual)) or set(actual) != expected:
                    raise ValueError(f"{hid}: {field} disagrees with member profiles")
        for field in ("focal_resident_id", "coordinator_id"):
            if profile.get(field) is not None and profile[field] not in decision_ids:
                raise ValueError(f"{hid}: {field} is not a decision-capable household member")
        if not (profile.get("focal_resident_id") or profile.get("coordinator_id")):
            raise ValueError(f"{hid}: missing focal/coordinator resident")
        count = shared.get("vehicle_count", 0)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError(f"{hid}: vehicle_count must be a nonnegative integer")
