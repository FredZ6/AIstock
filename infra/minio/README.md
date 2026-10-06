# Project-built MinIO dependency

The previous official Quay image now rejects pulls in CI. Compose builds MinIO
from the same official release source instead of requiring registry credentials.

- Upstream tag: `RELEASE.2025-09-07T16-13-09Z` (GitHub verified signed tag).
- Source commit: `07c3a429bfed433e49018cb0f78a52145d4bedeb`.
- Archive SHA-256: `8819e3e7817e46b7b3798f8f200ead208562e571563c2e040352378031abe9f2`.
- Builder and runtime base images are pinned to multi-platform digests.
- Go module checksums are verified by Go; `-mod=readonly` disallows dependency edits.
- The upstream entrypoint and AGPL license are preserved. This is a project-built
  binary from official source, not an official prebuilt image or a version upgrade.

Run `docker compose build minio` to verify the build. Normal `docker compose up`
builds the dependency; no Quay login or GitHub registry secret is required.
The first build downloads Go dependencies and takes longer than pulling a binary.
The existing MinIO volume name and service settings remain unchanged. A successful
build alone does not validate object storage; CI runs the repository integration
tests against a fresh container built from this Dockerfile.

To upgrade later, explicitly review and replace the source commit, archive checksum,
release labels and base digests together, then run the storage integration tests.
