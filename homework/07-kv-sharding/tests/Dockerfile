FROM rust:1.89-bookworm AS builder

RUN apt-get update && apt-get install -y build-essential python3-dev

WORKDIR /tests
COPY . .
RUN cargo install --path .
RUN rm -rf /tests

FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y python3-dev wget && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/cargo/bin/distsys-kv-sharding /usr/local/bin/distsys-kv-sharding

WORKDIR /anysystem/python
RUN wget https://raw.githubusercontent.com/systems-group/anysystem/refs/heads/main/python/anysystem.py
ENV PYTHONPATH="/anysystem/python"

WORKDIR /solution
ENTRYPOINT ["timeout", "-k", "10", "600", "distsys-kv-sharding", "-i", "node.py"]
