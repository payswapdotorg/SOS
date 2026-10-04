"""The ``/api/v1`` router assembly (directive §7 surface, exactly)."""
from __future__ import annotations

from fastapi import APIRouter

from . import (
    artifacts,
    auth,
    candidates,
    decisions,
    evidence,
    executions,
    experiments,
    health,
    jobs,
    learning,
    me,
    missions,
    providers,
    systems,
    workspaces,
)


def build_api_v1_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    router.include_router(health.router)
    router.include_router(auth.router)
    router.include_router(me.router)
    router.include_router(artifacts.router)
    router.include_router(workspaces.router)
    router.include_router(missions.router)
    router.include_router(systems.router)
    router.include_router(evidence.router)
    router.include_router(candidates.router)
    router.include_router(decisions.router)
    router.include_router(experiments.router)
    router.include_router(executions.router)
    router.include_router(learning.router)
    router.include_router(jobs.router)
    router.include_router(providers.router)
    return router
