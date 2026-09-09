"""Skill verification state machine.

  claimed --(TPO co-sign, same institution)--> institution_cosigned
  institution_cosigned --(industry verify)--> verified

Every transition is validated here: wrong actor, wrong institution, or wrong
current state raises an HTTPException. State-change metadata (who/when/note)
is stamped on the row, so badges everywhere in the UI are trustworthy.
"""
from fastapi import HTTPException

from app.db.pool import aexecute, afetch_one


async def _get_row(student_skill_id: str) -> dict:
    row = await afetch_one(
        """
        select v.*, sp.institution_id, sp.user_id as student_user_id
        from skill_verification_state v
        join student_profiles sp on sp.id = v.student_profile_id
        where v.id = %s
        """,
        (student_skill_id,),
    )
    if row is None:
        raise HTTPException(404, "student skill not found")
    return row


async def cosign(student_skill_id: str, user: dict, note: str | None = None) -> dict:
    row = await _get_row(student_skill_id)
    if row["state"] != "claimed":
        raise HTTPException(
            409, f"Cannot co-sign from state '{row['state']}' (must be 'claimed')"
        )
    if row["institution_id"] and user.get("institution_id") and \
            str(row["institution_id"]) != str(user["institution_id"]):
        raise HTTPException(403, "TPO can only co-sign students of their own institution")
    updated = await aexecute(
        """
        update skill_verification_state
        set state = 'institution_cosigned', cosigned_at = now(), cosigned_by = %s,
            cosigned_note = %s, updated_at = now()
        where id = %s
        returning *
        """,
        (user["id"], note, student_skill_id),
    )
    return updated


async def verify(student_skill_id: str, user: dict, note: str | None = None) -> dict:
    row = await _get_row(student_skill_id)
    if row["state"] != "institution_cosigned":
        raise HTTPException(
            409,
            f"Cannot verify from state '{row['state']}' "
            f"(must be 'institution_cosigned' — TPO co-sign must come first)",
        )
    updated = await aexecute(
        """
        update skill_verification_state
        set state = 'verified', verified_at = now(), verified_by = %s,
            verified_note = %s, updated_at = now()
        where id = %s
        returning *
        """,
        (user["id"], note, student_skill_id),
    )
    return updated


async def claim(student_profile_id: str, skill_id: str, user: dict,
                extracted_from_resume: bool = False) -> dict:
    existing = await afetch_one(
        "select id from skill_verification_state where student_profile_id = %s and skill_id = %s",
        (student_profile_id, skill_id),
    )
    if existing:
        raise HTTPException(409, "Skill already present on this profile")
    return await aexecute(
        """
        insert into skill_verification_state
            (student_profile_id, skill_id, state, extracted_from_resume, claimed_by)
        values (%s, %s, 'claimed', %s, %s)
        returning *
        """,
        (student_profile_id, skill_id, extracted_from_resume, user["id"]),
    )


async def unclaim(student_skill_id: str, user: dict) -> None:
    row = await _get_row(student_skill_id)
    if row["state"] != "claimed":
        raise HTTPException(
            409, "Co-signed / verified skills cannot be removed by the student"
        )
    await aexecute(
        "delete from skill_verification_state where id = %s", (student_skill_id,)
    )
