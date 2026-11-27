# Deploying the Reliability Reporter

How the server is set up, and how to rebuild it from nothing. Decisions and their reasons are in `docs/DECISIONS.md` (2026-11-26, Phase 3).

## The server

| What | Value |
|---|---|
| Google Cloud project | `social-commerce-reliability` |
| VM | `reporter-vm`, zone `us-central1-a`, machine type **e2-micro** (2 shared vCPUs, 1 GB RAM; Always Free) |
| OS | Ubuntu 24.04 LTS |
| Disk | 30 GB **standard** persistent disk (`pd-standard`, the only type the free tier covers; the console's default "balanced" disk is billed) |
| Public IP | static address `reporter-ip` = **34.68.212.170** (about $3.65/month: the one paid item) |
| Firewall | `default-allow-ssh` (22), `allow-web` (80, 443, for VMs tagged `web`), `default-allow-icmp` (ping), `default-allow-internal`. The default RDP rule (3389) was deleted. |
| Cloud permissions | **none**: the VM runs with no service account, so a break-in can't use it to reach other Google Cloud services |
| SSH keys | per-VM only (`block-project-ssh-keys=TRUE`): keys added to the project don't open this VM |

## Rebuilding it from nothing

1. **Create the address, the firewall rule and the VM** (from your Mac, logged in with `gcloud`):

   ```bash
   gcloud compute addresses create reporter-ip --region us-central1
   gcloud compute firewall-rules create allow-web --network default --direction INGRESS \
     --allow tcp:80,tcp:443 --source-ranges 0.0.0.0/0 --target-tags web
   gcloud compute firewall-rules delete default-allow-rdp   # Windows remote desktop: never needed

   gcloud compute instances create reporter-vm \
     --zone us-central1-a \
     --machine-type e2-micro \
     --image-family ubuntu-2404-lts-amd64 --image-project ubuntu-os-cloud \
     --boot-disk-size 30GB --boot-disk-type pd-standard \
     --address reporter-ip \
     --tags web \
     --no-service-account --no-scopes \
     --metadata block-project-ssh-keys=TRUE \
     --shielded-secure-boot --shielded-vtpm --shielded-integrity-monitoring
   ```

2. **Run the setup script** (SSH hardening, automatic security updates, 2 GB swap, Docker, the `deploy` user, `/opt/reporter`):

   ```bash
   gcloud compute scp deploy/server-setup.sh reporter-vm:~ --zone us-central1-a
   gcloud compute ssh reporter-vm --zone us-central1-a --command "sudo bash ~/server-setup.sh"
   ```

   The script is safe to run again; each step checks whether it's already done.

## Logging in

```bash
gcloud compute ssh reporter-vm --zone us-central1-a
```

`gcloud` creates an SSH key on your Mac the first time (`~/.ssh/google_compute_engine`) and adds its public half to this VM's metadata; Google's guest agent then installs it on the VM.

## What the setup script does, and why

| Step | Why |
|---|---|
| `PermitRootLogin no`, passwords off | Only key-based logins as a normal user; attackers constantly try passwords and `root` on every public server |
| Automatic security updates (`unattended-upgrades`, daily) | Security patches are installed without anyone remembering to |
| 2 GB swap, `vm.swappiness=10` | 1 GB of RAM is tight. Swap is an emergency overflow so a memory spike slows things down instead of the kernel killing a process; low swappiness keeps normal work in RAM |
| Docker from Docker's own apt repository | Ubuntu's own package lags behind; this is Docker's documented install method |
| Container logs: `local` driver, 10 MB × 3 files | Without rotation, logs grow until the disk is full |
| User `deploy` in the `docker` group, app folder `/opt/reporter` | CI logs in as `deploy` to run `docker compose`. **Being in the docker group is effectively root on this machine**, so the deploy user's SSH key must be guarded like a root password |

## Things to know

- **Docker and the firewall:** Docker's published ports bypass Ubuntu's `ufw` firewall. What protects the server is Google's cloud firewall (only 22/80/443 open) plus never publishing database ports in `compose.yaml`.
- **Costs:** the e2-micro, 30 GB standard disk and 1 GB/month of outbound traffic are free; the static IP is not. Stopping the VM does **not** stop the IP charge; releasing the address does (`gcloud compute addresses delete reporter-ip --region us-central1`).
