# Deploying to a DigitalOcean droplet (nginx + PostgreSQL)

Target: https://repair.acehill.co.ke  ·  Layout on the server:

    /opt/acehill/backend        Python code, .venv, .env      (runs as user "acehill", port 8010, localhost only)
    /var/www/acehill/frontend   built website files           (served by nginx)
    PostgreSQL database "acehill"                              (localhost only)

## 0. Look at what the droplet already runs
    sudo ss -tlnp | grep -E ':80 |:443 '    # which web server owns 80/443? (these steps assume nginx)
    python3 --version                         # needs 3.10+
    free -h                                   # this app needs roughly 200-300 MB RAM

## 1. DNS
Add an **A record**: name `repair`, value = the droplet's IP, at whoever hosts the DNS for acehill.co.ke
(your registrar, or DigitalOcean > Networking > Domains if the nameservers point there). Check:
    dig +short repair.acehill.co.ke

## 2. Packages and database (skip what is already installed)
    sudo apt update
    sudo apt install -y postgresql python3-venv nginx certbot python3-certbot-nginx rsync

    openssl rand -hex 24          # copy this output: it is the database password
    sudo -u postgres psql <<'SQL'
    CREATE USER acehill WITH PASSWORD 'PASTE_THE_PASSWORD_HERE';
    CREATE DATABASE acehill OWNER acehill;
    SQL

## 3. Server user and folders
    sudo useradd --system --create-home --home-dir /opt/acehill --shell /usr/sbin/nologin acehill
    sudo mkdir -p /var/www/acehill/frontend ~/acehill-upload

## 4. Upload the code (from YOUR machine, project root)
    SERVER=youruser@DROPLET_IP ./deploy/deploy.sh
The first run stops at the restart step, which is expected: the service does not exist yet. Continue below.

## 5. Backend environment (on the server)
    sudo -u acehill python3 -m venv /opt/acehill/backend/.venv
    sudo -u acehill /opt/acehill/backend/.venv/bin/pip install -r /opt/acehill/backend/requirements.txt

    python3 -c "import secrets; print(secrets.token_urlsafe(48))"      # -> SECRET_KEY
    sudo -u acehill nano /opt/acehill/backend/.env

    DATABASE_URL=postgresql://acehill:PASTE_THE_PASSWORD_HERE@localhost/acehill
    SECRET_KEY=<the long random string>
    SETUP_KEY=<a word only you know>
    ALLOWED_ORIGINS=https://repair.acehill.co.ke
    SHOP_TIMEZONE=Africa/Nairobi

    sudo chmod 600 /opt/acehill/backend/.env

## 6. Run it as a service
    # upload deploy/acehill-backend.service to the server first, e.g.:  scp deploy/* youruser@DROPLET_IP:~/
    sudo cp ~/acehill-backend.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now acehill-backend
    curl http://127.0.0.1:8010/health          # {"status":"ok"}
    sudo journalctl -u acehill-backend -n 50   # logs

## 7. nginx + HTTPS
    sudo cp ~/nginx-repair.acehill.co.ke.conf /etc/nginx/sites-available/repair.acehill.co.ke
    sudo ln -s /etc/nginx/sites-available/repair.acehill.co.ke /etc/nginx/sites-enabled/
    sudo nginx -t && sudo systemctl reload nginx
    sudo certbot --nginx -d repair.acehill.co.ke      # needs the DNS record from step 1 to be live

## 8. Create the admin straight away
Open https://repair.acehill.co.ke. Until the first admin exists, anyone who finds the site could claim it, so do this
immediately; the setup screen will ask for your SETUP_KEY.

## 9. Backups
    sudo cp ~/backup.sh /usr/local/bin/acehill-backup && sudo chmod +x /usr/local/bin/acehill-backup
    echo '30 2 * * * root /usr/local/bin/acehill-backup' | sudo tee /etc/cron.d/acehill-backup
    sudo /usr/local/bin/acehill-backup && ls -lh /var/backups/acehill
Also copy the dumps off the droplet now and then (or enable DigitalOcean droplet backups).
Restore: `gunzip -c file.sql.gz | sudo -u postgres psql acehill` into an empty database.

## Updating later
    SERVER=youruser@DROPLET_IP ./deploy/deploy.sh      # builds, uploads, restarts. Tables/columns upgrade automatically.

## Troubleshooting
* 502 Bad Gateway: the service is down. `sudo systemctl status acehill-backend` and `journalctl -u acehill-backend -n 80`.
* Blank page / API errors: browser dev tools > Network. Calls must go to `/api/...` on the same domain.
* certbot fails: DNS not live yet (`dig +short repair.acehill.co.ke`), or another site already owns that server_name.
