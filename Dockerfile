# Use an official Ubuntu 22.04 runtime as the parent image
FROM ubuntu:22.04

# Set a non-interactive mode for commands
ENV DEBIAN_FRONTEND=noninteractive

# Update apt, install all necessary packages, and clean up in one go
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    tmate \
    openssh-server \
    openssh-client \
    systemd \
    systemd-sysv \
    dbus \
    dbus-user-session \
    curl \
    ufw \
    net-tools \
    iproute2 \
    hostname && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Configure SSH for root login and set a password. This is for the container.
RUN sed -i 's/^#\?\s*PermitRootLogin\s\+.*/PermitRootLogin yes/' /etc/ssh/sshd_config && \
    echo 'root:root' | chpasswd

# Configure UFW firewall
RUN ufw allow 80 && ufw allow 443 && ufw --force enable

# Systemd is the main process, so set it as the entry point
# This ensures that systemd services (like sshd) start correctly
ENTRYPOINT ["/sbin/init"]

# CMD provides default arguments. We don't need any for a systemd entrypoint.
CMD []
