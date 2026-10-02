"""The adapter container: the single wiring point between the FastAPI app
and the provider seams (built by ``main.create_app`` from validated
``Settings``). Routes reach adapters ONLY through this container."""
from __future__ import annotations

from typing import Any

from .config import Settings


class ApiContainer:
    """Holds the wired provider seams + execution registry for one app."""

    def __init__(
        self,
        *,
        settings: Settings,
        persistence: Any,
        coordination: Any,
        artifacts: Any,
        execution_providers: dict[str, Any],
        github: Any,
    ) -> None:
        self.settings = settings
        self.persistence = persistence
        self.coordination = coordination
        self.artifacts = artifacts
        self.execution_providers = execution_providers
        self.github = github

    # -- truthful per-adapter health (never a fake ok) ---------------------

    def health_checks(self) -> dict[str, dict[str, str]]:
        persistence_health = self.persistence.health_check()
        coordination_health = self.coordination.health_check()
        artifacts_health = self.artifacts.health_check()
        execution_health = self._execution_health()
        github_health = self.github.health_check()
        return {
            "persistence": {
                "status": persistence_health.status,
                "mode": self.persistence.mode,
                "detail": persistence_health.detail,
            },
            "coordination": {
                "status": coordination_health.status,
                "mode": self.coordination.mode,
                "detail": coordination_health.detail,
            },
            "artifacts": {
                "status": artifacts_health.status,
                "mode": self.artifacts.mode,
                "detail": artifacts_health.detail,
            },
            "execution": {
                "status": execution_health["status"],
                "mode": self.settings.execution_mode,
                "detail": execution_health["detail"],
            },
        }

    def _execution_health(self) -> dict[str, str]:
        provider = self.execution_providers.get(self.settings.execution_mode)
        if provider is None:
            return {
                "status": "UNAVAILABLE",
                "detail": (
                    f"no execution provider registered under mode "
                    f"'{self.settings.execution_mode}'"
                ),
            }
        if self.settings.execution_mode == "demo":
            return {
                "status": "SUCCESS",
                "detail": (
                    "DemoProvider registered (always available; simulation "
                    "only, receipts demo:true)"
                ),
            }
        return {
            "status": "SUCCESS",
            "detail": f"execution provider '{provider.provider_id}' registered",
        }

    def provider_statuses(self) -> list[dict[str, Any]]:
        """Provider introspection for GET /providers/status (truthful)."""
        execution_provider = self.execution_providers.get(
            self.settings.execution_mode
        )
        statuses = [
            {
                "name": "persistence",
                "mode": self.persistence.mode,
                "implementation": self.persistence.implementation,
                "status": self.persistence.health_check().status,
                "detail": self.persistence.health_check().detail,
                "capabilities": [],
                "demo": self.persistence.mode == "local",
            },
            {
                "name": "coordination",
                "mode": self.coordination.mode,
                "implementation": self.coordination.implementation,
                "status": self.coordination.health_check().status,
                "detail": self.coordination.health_check().detail,
                "capabilities": [
                    "locks", "idempotency-keys", "rate-limit-buckets",
                ],
                "demo": self.coordination.mode == "local",
            },
            {
                "name": "artifacts",
                "mode": self.artifacts.mode,
                "implementation": self.artifacts.implementation,
                "status": self.artifacts.health_check().status,
                "detail": self.artifacts.health_check().detail,
                "capabilities": [
                    "content-addressed-store", "signed-urls",
                ],
                "demo": self.artifacts.mode == "local",
            },
            {
                "name": "execution",
                "mode": self.settings.execution_mode,
                "implementation": (
                    execution_provider.provider_id
                    if execution_provider is not None else "none"
                ),
                "status": self._execution_health()["status"],
                "detail": self._execution_health()["detail"],
                "capabilities": (
                    sorted(c.value for c in execution_provider.capabilities)
                    if execution_provider is not None else []
                ),
                "demo": self.settings.execution_mode == "demo",
            },
            {
                "name": "github",
                "mode": self.github.mode,
                "implementation": self.github.implementation,
                "status": self.github.health_check().status,
                "detail": self.github.health_check().detail,
                "capabilities": [
                    "resolve-repository", "list-branches", "list-commits",
                    "get-commit",
                ],
                "demo": self.github.mode == "local",
            },
        ]
        return statuses
