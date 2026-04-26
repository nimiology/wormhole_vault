# 🌌 Wormhole Vault

[![Status](https://img.shields.io/badge/status-active-success.svg)]()
[![Python](https://img.shields.io/badge/python-3.12-blue.svg)]()
[![Django](https://img.shields.io/badge/django-5.0-green.svg)]()
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)]()
[![License](https://img.shields.io/badge/license-MIT-lightgrey.svg)]()

**Wormhole Vault** is a high-performance, secure database backup manager designed to bridge the gap between your production servers and safe storage. It uses SSH tunneling to securely extract PostgreSQL dumps without exposing your database to the public internet.

---

## ✨ Features

- **🛡️ Secure Tunnels**: Automated SSH tunnel creation (localhost:15432 → remote:5432).
- **🐳 Docker Native**: Seamlessly pulls backups from remote Docker containers using `docker exec` via SSH.
- **⚙️ Automated Retention**: Configure how many days to keep backups; the vault cleans itself.
- **📊 Real-time Dashboard**: Monitor backup status, file sizes, and durations in a sleek, dark-themed UI.
- **⏰ Smart Scheduling**: Integrated Celery Beat for daily automated backups at your preferred hour.
- **📦 Compressed Storage**: All backups are automatically gzipped to save space.

---

## 🚀 Quick Start

### 1. Prerequisites
- Docker & Docker Compose
- SSH access to your target server
- PostgreSQL 15+ (on the target)

### 2. Installation
Clone the repository and move into the directory:
```bash
git clone https://github.com/nimiology/wormhole_vault.git
cd wormhole_vault
```

### 3. Configuration
Copy the environment template and fill in your details:
```bash
cp .env.example .env
```
Ensure you place your SSH private key in the `./ssh_keys/` directory.

### 4. Launch
Spin up the entire stack with a single command:
```bash
docker-compose up -d
```
Access the dashboard at `http://localhost:8585`.

---

## 🛠️ Architecture

Wormhole Vault is built on a modern stack for reliability and speed:
- **Backend**: Django + Django REST Framework
- **Tasks**: Celery + Redis
- **Database**: SQLite (Metadata storage)
- **Frontend**: Vanilla CSS + Semantic HTML (High-contrast Dark Mode)

---

## 🤝 Contributing

Contributions are welcome! If you have a feature request or found a bug, please open an issue or submit a pull request.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

<p align="center">
  Developed with ❤️ by <a href="https://github.com/nimiology">nimiology</a>
</p>
