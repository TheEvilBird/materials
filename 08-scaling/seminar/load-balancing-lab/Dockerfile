FROM rust:1.89-bookworm AS builder

RUN apt-get update && apt-get install -y build-essential python3-dev

WORKDIR /lab
COPY . .
RUN cargo install --path .
RUN rm -rf /lab

FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y python3-dev wget && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/cargo/bin/distsys-lb-lab /usr/local/bin/distsys-lb-lab

WORKDIR /lab
ENTRYPOINT ["distsys-lb-lab"]