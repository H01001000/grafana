FROM --platform=$BUILDPLATFORM golang@sha256:3889b425f035be855a72fb4755265311293b6d414521f0a519d819df32222d83 AS backend
ARG TARGETOS
ARG TARGETARCH
ARG TARGETVARIANT
ARG PROTOTYPE_REVISION=6193dc0331-crdb-prototype
RUN apk add --no-cache build-base git
WORKDIR /src
COPY . .
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    if [ "$TARGETARCH" = arm ]; then export GOARM="${TARGETVARIANT#v}"; fi; \
    CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH GOMAXPROCS=4 GOMEMLIMIT=3GiB \
    go build -buildvcs=false -p 4 -mod=readonly -tags oss \
    -ldflags "-s -w -X main.version=13.2.3-crdb-prototype -X main.commit=$PROTOTYPE_REVISION -X main.buildBranch=crdb-compat-v13.2.3" \
    -o /grafana ./pkg/cmd/grafana
FROM grafana/grafana@sha256:b28bae15e219c998fb0e0424ed724930cc61b1f61fb404d47c862f9a23f9e572
ARG PROTOTYPE_REVISION=6193dc0331-crdb-prototype
LABEL org.opencontainers.image.source="https://github.com/H01001000/grafana" \
      org.opencontainers.image.revision=$PROTOTYPE_REVISION \
      org.opencontainers.image.version="13.2.3-crdb-prototype"
USER root
COPY --from=backend --chmod=755 /grafana /usr/share/grafana/bin/grafana
COPY conf/defaults.ini /usr/share/grafana/conf/defaults.ini
USER 472
