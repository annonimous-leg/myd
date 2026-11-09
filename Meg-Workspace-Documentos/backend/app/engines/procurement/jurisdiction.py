from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procurement import JurisdictionProfile, JurisdictionInheritance


@dataclass(frozen=True)
class JurisdictionDecision:
    code: str
    authority: str
    government_level: str
    matter: str
    source: str
    portal_code: str | None = None
    profile_version: int = 1
    inherited_profiles: tuple[str, ...] = ()


class JurisdictionResolver:
    """Resolves only from explicit profiles and expands inheritance deterministically.

    Fail-closed policy for lookup chains used by ThresholdResolver / LegalRule:
    missing profiles do NOT raise during inheritance expansion — the chain
    degrades to the requested code so callers can return SIN_DETERMINAR /
    SIN_REGLA instead of exploding with ValueError.
    """

    async def load_profile(
        self,
        db: AsyncSession,
        tenant_id: UUID | str,
        code: str,
        *,
        required: bool = True,
    ) -> JurisdictionProfile | None:
        row = await db.scalar(
            select(JurisdictionProfile)
            .where(
                JurisdictionProfile.code == code.upper(),
                JurisdictionProfile.active.is_(True),
                or_(
                    JurisdictionProfile.tenant_id == tenant_id,
                    JurisdictionProfile.tenant_id.is_(None),
                ),
            )
            .order_by(JurisdictionProfile.tenant_id.desc().nullslast())
        )
        if row is None and required:
            raise ValueError(f"No existe perfil de jurisdicción activo: {code}")
        return row

    async def inheritance_codes(
        self,
        db: AsyncSession,
        tenant_id: UUID | str,
        code: str,
    ) -> tuple[str, ...]:
        """Expand inheritance without raising when a profile is missing.

        - Start with the requested code always present in the chain.
        - If the profile is absent, return (code,) — fail-closed for callers.
        - If a declared parent is absent, skip it (do not crash the chain).
        - Inheritance rows: tenant-specific OR global (tenant_id IS NULL).
        """
        root = str(code).upper().strip()
        if not root:
            return ()

        pending = [root]
        visited: list[str] = []

        while pending:
            current = pending.pop(0).upper()
            if current in visited:
                continue
            visited.append(current)

            profile = await self.load_profile(db, tenant_id, current, required=False)
            if profile is None:
                # No profile for this code: keep it in the chain so threshold /
                # rule queries can still match jurisdiction_code == current,
                # but do not attempt parent expansion.
                continue

            relations = (
                await db.execute(
                    select(JurisdictionInheritance)
                    .join(
                        JurisdictionProfile,
                        JurisdictionProfile.id == JurisdictionInheritance.child_profile_id,
                    )
                    .where(
                        JurisdictionProfile.code == current,
                        JurisdictionInheritance.active.is_(True),
                        or_(
                            JurisdictionInheritance.tenant_id == tenant_id,
                            JurisdictionInheritance.tenant_id.is_(None),
                        ),
                    )
                )
            ).scalars().all()

            parents: list[str] = []
            for relation in relations:
                parent = await db.get(JurisdictionProfile, relation.parent_profile_id)
                if parent is not None and parent.active:
                    parents.append(parent.code.upper())

            if not parents:
                parents = [
                    str(x).upper()
                    for x in (profile.ruleset or {}).get("inherits_from", [])
                    if x
                ]

            for parent_code in parents:
                if parent_code not in visited and parent_code not in pending:
                    # Only enqueue; missing parent is handled on visit (no raise).
                    pending.append(parent_code)

        return tuple(visited)

    async def resolve_db(
        self,
        db: AsyncSession,
        tenant_id: UUID | str,
        metadata: dict[str, Any],
    ) -> JurisdictionDecision:
        """Strict resolve for tender jurisdiction binding — requires a profile."""
        explicit = metadata.get("jurisdiction_code") or metadata.get("convocante_code")
        query = select(JurisdictionProfile).where(
            JurisdictionProfile.active.is_(True),
            or_(
                JurisdictionProfile.tenant_id == tenant_id,
                JurisdictionProfile.tenant_id.is_(None),
            ),
        )
        if explicit:
            query = query.where(JurisdictionProfile.code == str(explicit).upper())
        authority = str(metadata.get("authority", "")).strip()
        if not explicit and authority:
            query = query.where(JurisdictionProfile.authority.ilike(authority))
        profiles = (
            await db.execute(
                query.order_by(JurisdictionProfile.tenant_id.desc().nullslast())
            )
        ).scalars().all()
        if len(profiles) != 1:
            if not profiles:
                raise ValueError(
                    "No existe un perfil de jurisdicción activo para los metadatos proporcionados."
                )
            raise ValueError(
                "La jurisdicción es ambigua; se requiere un código explícito de perfil."
            )
        p = profiles[0]
        chain = await self.inheritance_codes(db, tenant_id, p.code)
        return JurisdictionDecision(
            code=p.code,
            authority=p.authority,
            government_level=p.government_level,
            matter=p.matter,
            source=(p.ruleset or {}).get("legal_source", "profile"),
            portal_code=p.portal_code,
            profile_version=p.profile_version,
            inherited_profiles=chain,
        )
