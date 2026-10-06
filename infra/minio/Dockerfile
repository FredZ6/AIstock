# Official RELEASE.2025-09-07T16-13-09Z source, independently built for this project.
FROM golang:1.24.7-bookworm@sha256:b8bae5bd9ba9b1f89b635c91c24cc75cea335a16fb5076310f38566fc674b1ec AS build
WORKDIR /src
RUN curl -fsSL --retry 3 https://codeload.github.com/minio/minio/tar.gz/07c3a429bfed433e49018cb0f78a52145d4bedeb -o /tmp/source.tar.gz \
    && echo '8819e3e7817e46b7b3798f8f200ead208562e571563c2e040352378031abe9f2  /tmp/source.tar.gz' | sha256sum -c - \
    && tar -xzf /tmp/source.tar.gz --strip-components=1
ENV CGO_ENABLED=0 GOTOOLCHAIN=local
RUN go build -mod=readonly -trimpath \
    -ldflags='-s -w -X github.com/minio/minio/cmd.Version=2025-09-07T16:13:09Z -X github.com/minio/minio/cmd.ReleaseTag=RELEASE.2025-09-07T16-13-09Z -X github.com/minio/minio/cmd.CommitID=07c3a429bfed433e49018cb0f78a52145d4bedeb -X github.com/minio/minio/cmd.ShortCommitID=07c3a429bfed4' \
    -o /out/minio .

FROM debian:bookworm-slim@sha256:7c7b2c966bc9ee8cedfeef67e0e279108992c77681fa595db4a9d65c06ccc587
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /out/minio /usr/bin/minio
COPY --from=build /src/LICENSE /usr/share/licenses/minio/LICENSE
COPY --from=build /src/dockerscripts/docker-entrypoint.sh /usr/bin/docker-entrypoint.sh
LABEL org.opencontainers.image.source="https://github.com/minio/minio" \
      org.opencontainers.image.revision="07c3a429bfed433e49018cb0f78a52145d4bedeb" \
      org.opencontainers.image.licenses="AGPL-3.0-only"
ENTRYPOINT ["/usr/bin/docker-entrypoint.sh"]
CMD ["minio"]
