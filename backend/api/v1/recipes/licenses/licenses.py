# api/v1/licenses/router.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from database.main.core.session import get_async_session
from database.main.core.models import License, User
from api.v1.auth.utils.dependencies import get_current_user
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix='/licenses', tags=['Recipe Licenses'])


# ── Schemas ───────────────────────────────────────────────

class LicenseIn(BaseModel):
    code:  str
    title: str
    desc:  str
    text:  Optional[str] = None
    url:   Optional[str] = None


class LicenseOut(BaseModel):
    id:    int
    code:  str
    title: str
    desc:  str
    text:  Optional[str]
    url:   Optional[str]

    class Config:
        from_attributes = True


LICENSES_SEED: list[dict] = [
    # ── Creative Commons ──────────────────────────────────
    {
        "code":  "cc0",
        "title": "CC0 1.0 Universal - Public Domain Dedication",
        "desc":  "No rights reserved. Free to use, modify, and distribute for any purpose without attribution.",
        "text":  (
            "The person who associated a work with this deed has dedicated the work to the public domain "
            "by waiving all of his or her rights to the work worldwide under copyright law, including all "
            "related and neighboring rights, to the extent allowed by law. You can copy, modify, distribute "
            "and perform the work, even for commercial purposes, all without asking permission."
        ),
        "url": "https://creativecommons.org/publicdomain/zero/1.0/",
    },
    {
        "code":  "cc-by-4.0",
        "title": "Creative Commons Attribution 4.0 International",
        "desc":  "Share and adapt freely for any purpose, including commercially, with credit to the author.",
        "text":  (
            "You are free to share (copy and redistribute the material in any medium or format) and adapt "
            "(remix, transform, and build upon the material) for any purpose, even commercially, as long as "
            "you give appropriate credit, provide a link to the license, and indicate if changes were made."
        ),
        "url": "https://creativecommons.org/licenses/by/4.0/",
    },
    {
        "code":  "cc-by-sa-4.0",
        "title": "Creative Commons Attribution-ShareAlike 4.0 International",
        "desc":  "Share and adapt for any purpose with attribution, but forks must use the same license.",
        "text":  (
            "You are free to share and adapt the material for any purpose, even commercially, under the "
            "following terms: Attribution - give appropriate credit. ShareAlike - if you remix or transform "
            "the material, you must distribute your contributions under the same license as the original."
        ),
        "url": "https://creativecommons.org/licenses/by-sa/4.0/",
    },
    {
        "code":  "cc-by-nd-4.0",
        "title": "Creative Commons Attribution-NoDerivatives 4.0 International",
        "desc":  "Share freely with attribution, but no modifications or adaptations are allowed.",
        "text":  (
            "You are free to share (copy and redistribute the material in any medium or format) for any "
            "purpose, even commercially, as long as you give appropriate credit. However, if you remix, "
            "transform, or build upon the material, you may not distribute the modified material."
        ),
        "url": "https://creativecommons.org/licenses/by-nd/4.0/",
    },
    {
        "code":  "cc-by-nc-4.0",
        "title": "Creative Commons Attribution-NonCommercial 4.0 International",
        "desc":  "Share and adapt with attribution, but only for non-commercial purposes.",
        "text":  (
            "You are free to share and adapt the material under the following terms: Attribution - give "
            "appropriate credit. NonCommercial - you may not use the material for commercial purposes. "
            "No additional restrictions may be applied."
        ),
        "url": "https://creativecommons.org/licenses/by-nc/4.0/",
    },
    {
        "code":  "cc-by-nc-sa-4.0",
        "title": "Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International",
        "desc":  "Non-commercial use only, with attribution, and forks must carry the same license.",
        "text":  (
            "You are free to share and adapt the material for non-commercial purposes only, under the "
            "following terms: Attribution - give appropriate credit. NonCommercial - not for commercial use. "
            "ShareAlike - distribute adaptations under the same license."
        ),
        "url": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
    },
    {
        "code":  "cc-by-nc-nd-4.0",
        "title": "Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International",
        "desc":  "Most restrictive CC license - share only, non-commercial, no modifications, with attribution.",
        "text":  (
            "The most restrictive Creative Commons license. You may only download and share the work for "
            "non-commercial purposes and with attribution. You may not change the work in any way or use "
            "it commercially."
        ),
        "url": "https://creativecommons.org/licenses/by-nc-nd/4.0/",
    },

    # ── All Rights Reserved ───────────────────────────────
    {
        "code":  "all-rights-reserved",
        "title": "All Rights Reserved",
        "desc":  "Full copyright retained. No use, reproduction, or adaptation without explicit permission.",
        "text":  (
            "The author retains full copyright. No part of this recipe may be reproduced, distributed, or "
            "transmitted in any form or by any means without the prior written permission of the author, "
            "except in the case of brief quotations for review purposes."
        ),
        "url":  None,
    },

    # ── Open / permissive ─────────────────────────────────
    {
        "code":  "mit",
        "title": "MIT License",
        "desc":  "Extremely permissive - use, copy, modify, and distribute freely with attribution.",
        "text":  (
            "Permission is hereby granted, free of charge, to any person obtaining a copy of this work "
            "to deal in the work without restriction, including without limitation the rights to use, copy, "
            "modify, merge, publish, distribute, sublicense, and/or sell copies of the work, subject to "
            "the condition that the above copyright notice and this permission notice shall be included in "
            "all copies or substantial portions of the work."
        ),
        "url": "https://opensource.org/licenses/MIT",
    },
    {
        "code":  "odc-by-1.0",
        "title": "Open Data Commons Attribution License 1.0",
        "desc":  "Open data license - share, create, and adapt freely with attribution to the source.",
        "text":  (
            "You are free to share, create, and adapt this work as long as you attribute the work in the "
            "manner specified by the author. This license is designed for data and databases."
        ),
        "url": "https://opendatacommons.org/licenses/by/1-0/",
    },
    {
        "code":  "odc-odbl-1.0",
        "title": "Open Database License (ODbL) 1.0",
        "desc":  "Share and adapt databases freely, but adapted databases must remain open under ODbL.",
        "text":  (
            "You are free to share and adapt this database, as long as you attribute the source, "
            "share-alike any adapted databases under ODbL, and keep the database open (if you redistribute)."
        ),
        "url": "https://opendatacommons.org/licenses/odbl/1-0/",
    },

    # ── Platform-specific / editorial ────────────────────
    {
        "code":  "forkit-open",
        "title": "Forkit Open Recipe License",
        "desc":  "Fork and adapt freely on Forkit with attribution. Commercial use outside Forkit requires permission.",
        "text":  (
            "This recipe is freely available for personal use, forking, and adaptation on the Forkit "
            "platform. Forks must credit the original author. Commercial use outside Forkit requires "
            "separate written permission from the original author."
        ),
        "url": "https://forkit.up.railway.app/licenses/forkit-open",
    },
    {
        "code":  "forkit-attribution",
        "title": "Forkit Attribution License",
        "desc":  "Fork and publish on Forkit with visible credit to the original author. No commercial use.",
        "text":  (
            "You may fork, adapt, and publish this recipe on Forkit with attribution to the original author. "
            "The original recipe title and author name must appear on all forks. No commercial use permitted "
            "without prior consent."
        ),
        "url": "https://forkit.up.railway.app/licenses/forkit-attribution",
    },
    {
        "code":  "personal-only",
        "title": "Personal Use Only",
        "desc":  "Personal, non-commercial use only. Social sharing with credit is fine; redistribution is not.",
        "text":  (
            "This recipe is shared for personal, non-commercial use only. It may not be republished, "
            "redistributed, or adapted for commercial purposes. Sharing on social media with credit "
            "to the author is permitted."
        ),
        "url": None,
    },
]


# ── Admin guard ───────────────────────────────────────────

def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return user


# ── GET /licenses/ - public, list all ────────────────────

@router.get("/", response_model=list[LicenseOut])
async def list_licenses(
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(select(License).order_by(License.id))
    return result.scalars().all()


# ── POST /licenses/ - admin, create one ──────────────────

@router.post("/", response_model=LicenseOut, status_code=201)
async def create_license(
    payload: LicenseIn,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_async_session),
):
    existing = await session.execute(
        select(License).where(License.code == payload.code)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"License with code '{payload.code}' already exists")

    lic = License(**payload.model_dump())
    session.add(lic)
    await session.commit()
    await session.refresh(lic)
    return lic


# ── POST /licenses/bulk - admin, upsert many ─────────────

@router.post("/bulk", response_model=list[LicenseOut], status_code=201)
async def bulk_upsert_licenses(
    payload: list[LicenseIn] = LICENSES_SEED,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_async_session),
):
    if not payload:
        raise HTTPException(status_code=400, detail="Empty payload")
    if len(payload) > 100:
        raise HTTPException(status_code=400, detail="Max 100 licenses per bulk call")

    rows = [p.model_dump() for p in payload]

    stmt = (
        insert(License)
        .values(rows)
        .on_conflict_do_update(
            index_elements=["code"],
            set_={
                "title": insert(License).excluded.title,
                "desc":  insert(License).excluded.desc,
                "text":  insert(License).excluded.text,
                "url":   insert(License).excluded.url,
            },
        )
        .returning(License)
    )

    result = await session.execute(stmt)
    await session.commit()
    return result.scalars().all()


# ── DELETE /licenses/{code} - admin ──────────────────────

@router.delete("/{code}", status_code=204)
async def delete_license(
    code: str,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_async_session),
):
    lic = await session.execute(select(License).where(License.code == code))
    lic = lic.scalar_one_or_none()
    if not lic:
        raise HTTPException(status_code=404, detail="License not found")
    await session.delete(lic)
    await session.commit()