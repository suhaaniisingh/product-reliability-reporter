#!/usr/bin/env bash
# One-time setup of the Reliability Reporter server (Ubuntu 24.04 LTS on a Google Cloud e2-micro).
# Safe to run again: every step checks whether it's already done. See docs/DEPLOY.md.
#
#   gcloud compute scp deploy/server-setup.sh reporter-vm:~ --zone us-central1-a
#   gcloud compute ssh reporter-vm --zone us-central1-a --command "sudo bash ~/server-setup.sh"
set -euo pipefail

if [[ $EUID -ne 0 ]]; then echo "Run with sudo." >&2; exit 1; fi

step() { echo; echo "==> $*"; }

step "SSH: keys only, no root login"
# Ubuntu's cloud image already disables passwords; we also forbid root over SSH entirely.
cat > /etc/ssh/sshd_config.d/99-reporter.conf <<'EOF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
EOF
sshd -t && systemctl reload ssh

step "Automatic security updates"
# Already on in Ubuntu's cloud image; made explicit so a rebuilt server can't miss it.
apt-get update -q
apt-get install -y -q unattended-upgrades
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF

step "Swap: 2 GB (the machine has only 1 GB of RAM)"
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
# Prefer RAM; only use swap under real memory pressure.
echo 'vm.swappiness=10' > /etc/sysctl.d/99-reporter.conf
sysctl -q --system

step "Docker Engine + compose plugin (from Docker's official apt repository)"
if ! command -v docker >/dev/null; then
  apt-get install -y -q ca-certificates curl
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -q
  apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
# Rotate container logs so they can't fill the 30 GB disk.
mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<'EOF'
{
  "log-driver": "local",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
EOF
systemctl enable --now docker
systemctl restart docker

step "Deploy user and app folder"
# CI logs in as 'deploy' to run docker compose. Being in the docker group is effectively
# root on this machine, so this user's SSH key is the most sensitive secret we have.
id deploy >/dev/null 2>&1 || adduser --disabled-password --gecos "" deploy
usermod -aG docker deploy
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
touch /home/deploy/.ssh/authorized_keys
chown deploy:deploy /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys
install -d -m 750 -o deploy -g deploy /opt/reporter

step "Done"
docker --version
docker compose version
free -m | head -3
