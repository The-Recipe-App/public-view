import asyncio
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.main.core.session import get_async_session
from database.main.core.models import Policy, PolicyVersion

from utilities.common.common_utility import debug_print

# -------------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
# ✅ Seeder reads from REAL DISK path here:
DISK_STATIC_DIR = BASE_DIR / "static" / "legal"

# ✅ Stored URL must ALWAYS look like this:
PUBLIC_STATIC_BASE = "/static/legal"

VERSION = "v1"
LOCALE = "en"

EFFECTIVE_AT = datetime(2026, 1, 28, tzinfo=timezone.utc)

POLICY_DEFS = [
    {
        "key": "tos",
        "title": "Terms of Service",
        "description": "Governs use of the Forkit platform",
        "filename": "tos.md",
    },
    {
        "key": "privacy",
        "title": "Privacy Policy",
        "description": "How Forkit processes personal data",
        "filename": "privacy.md",
    },
    {
        "key": "community_guidelines",
        "title": "Community Guidelines",
        "description": "Platform behavior rules",
        "filename": "cg.md",
    },
    {
        "key": "cookie_policy",
        "title": "Cookie Policy",
        "description": "Governs use of cookies",
        "filename": "cookie_policy.md",
    },
    {
        "key": "license",
        "title": "Forkit License",
        "description": "Forkit open source license",
        "filename": "LICENSE.md",
    },
]


# -------------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------------

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# -------------------------------------------------------------------
# SEEDER
# -------------------------------------------------------------------

async def seed_policy(session: AsyncSession, cfg: dict):
    filename = cfg["filename"]

    # ============================================================
    # 1. Read policy file from disk
    # ============================================================

    disk_path = DISK_STATIC_DIR / VERSION / filename

    if not disk_path.exists():
        raise FileNotFoundError(
            f"\n❌ Missing policy file on disk: {disk_path}"
        )

    contents = disk_path.read_text(encoding="utf-8")
    text_hash = sha256(contents)

    public_url = f"{PUBLIC_STATIC_BASE}/{VERSION}/{filename}"

    debug_print(
        f"Checking policy '{cfg['key']}'...",
        color="cyan",
        tag="SEEDER"
    )

    # ============================================================
    # 2. Get or create Policy container
    # ============================================================

    res = await session.execute(
        select(Policy).where(Policy.key == cfg["key"])
    )
    policy = res.scalar_one_or_none()

    if not policy:
        debug_print(
            f"Creating new Policy container: {cfg['key']}",
            color="yellow",
            tag="SEEDER"
        )

        policy = Policy(
            key=cfg["key"],
            title=cfg["title"],
            description=cfg["description"],
        )
        session.add(policy)
        await session.flush()

    # ============================================================
    # 3. Check active PolicyVersion
    # ============================================================

    res = await session.execute(
        select(PolicyVersion)
        .where(
            PolicyVersion.policy_id == policy.id,
            PolicyVersion.is_active == True
        )
    )
    active_version = res.scalar_one_or_none()

    # ============================================================
    # 4. Skip if nothing changed
    # ============================================================

    if active_version:
        if (
            active_version.text_hash == text_hash
            and active_version.file_url == public_url
            and active_version.version == VERSION
            and active_version.locale == LOCALE
        ):
            debug_print(
                f"✅ No changes for '{cfg['key']}' — skipping",
                color="green",
                tag="SEEDER"
            )
            return

        debug_print(
            f"⚠ Policy '{cfg['key']}' changed → creating new version",
            color="magenta",
            tag="SEEDER"
        )

    else:
        debug_print(
            f"🌱 No active version found → seeding first version",
            color="yellow",
            tag="SEEDER"
        )

    # ============================================================
    # 5. Deactivate old versions ONLY if inserting new
    # ============================================================

    await session.execute(
        update(PolicyVersion)
        .where(PolicyVersion.policy_id == policy.id)
        .values(is_active=False)
    )

    # ============================================================
    # 6. Insert new immutable PolicyVersion
    # ============================================================

    version_row = PolicyVersion(
        policy_id=policy.id,
        version=VERSION,
        locale=LOCALE,
        file_url=public_url,
        text_hash=text_hash,
        effective_at=EFFECTIVE_AT,
        is_active=True,
        notes="Static-file based policy reference",
    )

    session.add(version_row)
    await session.commit()

    debug_print(
        f"✅ Seeded '{cfg['key']}' → new version stored: {public_url}",
        color="green",
        tag="SEEDER"
    )


async def ensure_legal_policies():
    async for session in get_async_session():
        for cfg in POLICY_DEFS:
            await seed_policy(session, cfg)
        break

