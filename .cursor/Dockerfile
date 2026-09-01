FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        ffmpeg \
        file \
        git \
        jq \
        python3 \
    && rm -rf /var/lib/apt/lists/*
