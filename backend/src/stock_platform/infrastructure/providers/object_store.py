"""Raw payload persistence backed by the project-local MinIO service."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from io import BytesIO
from typing import Protocol, cast

from stock_platform.settings import Settings


class MinioClient(Protocol):
    def bucket_exists(self, bucket_name: str) -> bool: ...

    def make_bucket(self, bucket_name: str) -> None: ...

    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: BytesIO,
        length: int,
        content_type: str,
    ) -> object: ...

    def list_objects(
        self,
        bucket_name: str,
        prefix: str,
        recursive: bool,
    ) -> Iterable[MinioObject]: ...


class MinioResponse(Protocol):
    def read(self) -> bytes: ...

    def close(self) -> None: ...

    def release_conn(self) -> None: ...


class MinioReadableClient(Protocol):
    def get_object(self, bucket_name: str, object_name: str) -> MinioResponse: ...


class MinioObject(Protocol):
    object_name: str | None


class MinioRawObjectStore:
    def __init__(self, *, client: MinioClient, bucket: str) -> None:
        self._client = client
        self._bucket = bucket
        if not self._client.bucket_exists(bucket):
            self._client.make_bucket(bucket)

    @classmethod
    def from_settings(cls, settings: Settings) -> MinioRawObjectStore:
        from minio import Minio

        client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        return cls(client=cast(MinioClient, client), bucket=settings.minio_bucket)

    def put(self, object_key: str, content: bytes, content_type: str) -> None:
        self._client.put_object(
            self._bucket,
            object_key,
            BytesIO(content),
            len(content),
            content_type,
        )

    def list_keys(self, prefix: str = "") -> tuple[str, ...]:
        return tuple(sorted(self.iter_keys(prefix)))

    def iter_keys(self, prefix: str = "") -> Iterator[str]:
        for item in self._client.list_objects(
            self._bucket,
            prefix=prefix,
            recursive=True,
        ):
            if item.object_name is not None:
                yield item.object_name

    def get(self, object_key: str) -> bytes:
        response = cast(MinioReadableClient, self._client).get_object(self._bucket, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()
