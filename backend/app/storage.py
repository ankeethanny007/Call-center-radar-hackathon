"""Audio storage abstraction: local development or private Supabase Storage."""
from __future__ import annotations

from pathlib import Path, PurePosixPath
from threading import Lock
from time import monotonic
from urllib.parse import quote

import httpx

from .config import settings
from .security import signed_media_query


class MediaStorage:
    def __init__(self) -> None:
        self._signed_urls: dict[str, tuple[float, str]] = {}
        self._signed_urls_lock = Lock()

    @staticmethod
    def _object_name(relative_path: str) -> str:
        """Reject paths that could escape a local media root or storage prefix."""
        if not relative_path or "\\" in relative_path:
            raise ValueError("Audio object path must be a non-empty POSIX relative path")
        path = PurePosixPath(relative_path)
        if path.is_absolute() or ".." in path.parts or str(path) in ("", "."):
            raise ValueError("Audio object path must stay within the configured media root")
        return path.as_posix()

    def _local_path(self, relative_path: str, media_root: Path) -> Path:
        object_name = self._object_name(relative_path)
        root = media_root.resolve()
        source = (root / object_name).resolve()
        if root not in source.parents:
            raise ValueError("Audio object path must stay within the configured media root")
        return source

    def url_for(self, relative_path: str) -> str:
        object_name = self._object_name(relative_path)
        if settings.storage_provider.lower() == "supabase":
            if not settings.supabase_url or not settings.supabase_service_key:
                raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY are required for private Supabase Storage")
            base = settings.supabase_url.rstrip("/")
            with self._signed_urls_lock:
                cached = self._signed_urls.get(object_name)
                if cached and cached[0] > monotonic():
                    return cached[1]
            endpoint = f"{base}/storage/v1/object/sign/{settings.supabase_bucket}/{quote(object_name, safe='/')}"
            headers = {"authorization": f"Bearer {settings.supabase_service_key}", "apikey": settings.supabase_service_key}
            expires_in = max(60, settings.media_url_ttl_seconds)
            response = httpx.post(endpoint, headers=headers, json={"expiresIn": expires_in}, timeout=15)
            response.raise_for_status()
            signed_path = response.json()["signedURL"]
            signed_url = signed_path if signed_path.startswith("http") else f"{base}/storage/v1{signed_path}"
            with self._signed_urls_lock:
                self._signed_urls[object_name] = (monotonic() + max(30, expires_in - 30), signed_url)
            return signed_url
        return f"/media/{quote(object_name, safe='/')}{signed_media_query(object_name)}"

    def upload(self, relative_path: str, source: Path) -> None:
        """Upload an original MP3 once. Requires a server-side Supabase service key."""
        object_name = self._object_name(relative_path)
        if settings.storage_provider.lower() != "supabase":
            return
        if not settings.supabase_url or not settings.supabase_service_key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY are required for upload")
        if not source.is_file():
            raise FileNotFoundError(f"Recording is missing: {source}")
        url = f"{settings.supabase_url.rstrip('/')}/storage/v1/object/{settings.supabase_bucket}/{quote(object_name, safe='/')}"
        headers = {"authorization": f"Bearer {settings.supabase_service_key}", "apikey": settings.supabase_service_key, "x-upsert": "true", "content-type": "audio/mpeg"}
        with source.open("rb") as stream:
            response = httpx.post(url, headers=headers, content=stream.read(), timeout=120)
        response.raise_for_status()

    def download(self, relative_path: str, destination: Path) -> Path:
        """Download a private remote recording to an ephemeral worker location."""
        object_name = self._object_name(relative_path)
        if settings.storage_provider.lower() != "supabase":
            raise FileNotFoundError(
                f"Recording is missing from local media storage: {object_name}. "
                "Configure Supabase Storage or mount the original recording."
            )

        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(f".{destination.name}.partial")
        try:
            with httpx.stream("GET", self.url_for(object_name), follow_redirects=True, timeout=120) as response:
                response.raise_for_status()
                with partial.open("wb") as stream:
                    for chunk in response.iter_bytes():
                        stream.write(chunk)
            partial.replace(destination)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
        return destination

    def materialize(self, relative_path: str, media_root: Path, scratch_dir: Path) -> Path:
        """Return a local source path, downloading only when the original is absent.

        The downloaded copy lives under the caller-owned scratch directory so a
        hosted worker never persists a second copy of private call audio.
        """
        source = self._local_path(relative_path, media_root)
        if source.is_file():
            return source
        return self.download(relative_path, scratch_dir / "source.mp3")


storage = MediaStorage()
