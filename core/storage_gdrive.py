"""Google Drive project storage (planned; see README "Roadmap")."""
from core.storage import ProjectStore


class DriveStore(ProjectStore):  # pragma: no cover - not implemented yet
    @classmethod
    def from_settings(cls) -> "DriveStore":
        raise NotImplementedError(
            "Google Drive storage is not available yet. Set STORAGE_BACKEND = \"local\"."
        )
