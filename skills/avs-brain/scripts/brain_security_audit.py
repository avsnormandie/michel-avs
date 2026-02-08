#!/usr/bin/env python3
"""
Brain Security Audit - Infrastructure security scanner

Usage:
    brain_security_audit.py audit [--local] [--remote] [--send]
    brain_security_audit.py certs [--send]
    brain_security_audit.py fixes

Audits GK41 local security + remote OVH servers.
"""

import argparse
import json
import logging
import os
import re
import socket
import ssl
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# Setup logging
LOG_DIR = Path(os.environ.get('MICHEL_LOG_DIR', os.path.expanduser('~/michel-avs/logs')))
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'brain_security_audit.log'),
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger('brain_security_audit')

# Config
HISTORY_FILE = LOG_DIR / 'security_audit_history.jsonl'
AVS_INTRANET_URL = os.environ.get('AVS_INTRANET_URL', 'https://intra.avstech.fr')
AVS_API_KEY = os.environ.get('AVS_API_KEY', '')

# Servers to audit
HTTPS_SERVERS = {
    'intra.avstech.fr': {'ip': '141.95.154.151', 'name': 'web-server-avs'},
    'api.logics-cloud.fr': {'ip': '54.38.46.25', 'name': 'logics-db-server'},
    'n8n.avstech.fr': {'ip': '141.95.154.151', 'name': 'n8n'},
}

ALL_SERVERS = {
    'web-server-avs': {'host': '141.95.154.151', 'ports': [22, 80, 443]},
    'logics-db-server': {'host': '54.38.46.25', 'ports': [22, 80, 443, 4900, 5432, 3306]},
    'logics-save-server': {'host': '51.255.65.118', 'ports': [22, 80, 443, 21, 2111]},
    'api-server': {'host': '51.178.18.80', 'ports': [22, 80, 443, 8055]},
}

REQUIRED_HEADERS = ['strict-transport-security', 'x-frame-options', 'x-content-type-options']

# Severity weights for scoring
SEVERITY_WEIGHT = {'CRITIQUE': 15, 'HAUTE': 8, 'MOYENNE': 3, 'FAIBLE': 1, 'OK': 0}


def api_request(endpoint, method='GET', data=None):
    """Make API request to AVS Intranet"""
    if not AVS_API_KEY:
        return {'success': False, 'error': 'AVS_API_KEY not configured'}
    url = f"{AVS_INTRANET_URL}/api/external/{endpoint}"
    headers = {
        'Content-Type': 'application/json; charset=utf-8',
        'X-API-Key': AVS_API_KEY
    }
    req_data = json.dumps(data).encode('utf-8') if data else None
    try:
        req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        return {'success': False, 'error': str(e)}


def send_alert(message):
    """Send alert via Telegram"""
    logger.info("Sending report to Telegram")
    api_request('michel', method='POST', data={
        'message': message,
        'from': 'Security Audit'
    })


def append_history(entry):
    """Append audit result to history"""
    with open(HISTORY_FILE, 'a') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')


# --- Local checks (GK41) ---

def check_open_ports():
    """Check listening ports on all interfaces"""
    findings = []
    try:
        result = subprocess.run(['ss', '-tlnp'], capture_output=True, text=True, timeout=10)
        exposed = []
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 4:
                addr = parts[3]
                if addr.startswith('0.0.0.0:') or addr.startswith('*:') or addr.startswith('[::]:'):
                    port = addr.rsplit(':', 1)[-1]
                    exposed.append(port)

        if exposed:
            findings.append({
                'check': 'Ports ouverts sur 0.0.0.0',
                'status': 'MOYENNE' if len(exposed) <= 3 else 'HAUTE',
                'detail': f"Ports exposes: {', '.join(exposed)}",
                'ports': exposed
            })
        else:
            findings.append({
                'check': 'Ports ouverts sur 0.0.0.0',
                'status': 'OK',
                'detail': 'Aucun port expose sur toutes les interfaces'
            })
    except Exception as e:
        findings.append({'check': 'Ports ouverts', 'status': 'FAIBLE', 'detail': f'Erreur: {e}'})
    return findings


def check_ssh_config():
    """Audit SSH server configuration"""
    findings = []
    try:
        with open('/etc/ssh/sshd_config', 'r') as f:
            config = f.read()

        # Password auth
        if re.search(r'^\s*PasswordAuthentication\s+no', config, re.MULTILINE):
            findings.append({'check': 'SSH PasswordAuth', 'status': 'OK', 'detail': 'Desactive'})
        else:
            findings.append({'check': 'SSH PasswordAuth', 'status': 'CRITIQUE', 'detail': 'Actif ou non defini'})

        # Root login
        if re.search(r'^\s*PermitRootLogin\s+no', config, re.MULTILINE):
            findings.append({'check': 'SSH PermitRootLogin', 'status': 'OK', 'detail': 'Desactive'})
        elif re.search(r'^\s*PermitRootLogin\s+prohibit-password', config, re.MULTILINE):
            findings.append({'check': 'SSH PermitRootLogin', 'status': 'FAIBLE', 'detail': 'prohibit-password (acceptable)'})
        else:
            findings.append({'check': 'SSH PermitRootLogin', 'status': 'MOYENNE', 'detail': 'Non explicitement desactive (defaut: prohibit-password)'})

        # Port
        port_match = re.search(r'^\s*Port\s+(\d+)', config, re.MULTILINE)
        if port_match and port_match.group(1) != '22':
            findings.append({'check': 'SSH Port', 'status': 'OK', 'detail': f'Port non standard: {port_match.group(1)}'})
        else:
            findings.append({'check': 'SSH Port', 'status': 'FAIBLE', 'detail': 'Port 22 par defaut'})

        # X11Forwarding
        if re.search(r'^\s*X11Forwarding\s+yes', config, re.MULTILINE):
            findings.append({'check': 'SSH X11Forwarding', 'status': 'MOYENNE', 'detail': 'Active (risque potentiel)'})
        else:
            findings.append({'check': 'SSH X11Forwarding', 'status': 'OK', 'detail': 'Desactive'})

        # AllowUsers
        if re.search(r'^\s*AllowUsers', config, re.MULTILINE):
            findings.append({'check': 'SSH AllowUsers', 'status': 'OK', 'detail': 'Restriction par utilisateur'})
        else:
            findings.append({'check': 'SSH AllowUsers', 'status': 'FAIBLE', 'detail': 'Pas de restriction AllowUsers'})

    except PermissionError:
        findings.append({'check': 'SSH Config', 'status': 'FAIBLE', 'detail': 'Impossible de lire sshd_config (pas root)'})
    except Exception as e:
        findings.append({'check': 'SSH Config', 'status': 'FAIBLE', 'detail': f'Erreur: {e}'})
    return findings


def check_firewall():
    """Check if firewall is active"""
    findings = []
    try:
        result = subprocess.run(['sudo', '-n', 'ufw', 'status'], capture_output=True, text=True, timeout=10)
        if 'active' in result.stdout.lower():
            findings.append({'check': 'Firewall UFW', 'status': 'OK', 'detail': 'Actif'})
        elif result.returncode != 0:
            # Try without sudo
            result2 = subprocess.run(['ufw', 'status'], capture_output=True, text=True, timeout=10)
            if 'active' in result2.stdout.lower():
                findings.append({'check': 'Firewall UFW', 'status': 'OK', 'detail': 'Actif'})
            else:
                findings.append({'check': 'Firewall UFW', 'status': 'CRITIQUE', 'detail': 'Inactif ou non installe'})
        else:
            findings.append({'check': 'Firewall UFW', 'status': 'CRITIQUE', 'detail': 'Inactif'})
    except Exception:
        # Fallback: check if ufw process exists
        try:
            result = subprocess.run(['systemctl', 'is-active', 'ufw'], capture_output=True, text=True, timeout=5)
            if result.stdout.strip() == 'active':
                findings.append({'check': 'Firewall UFW', 'status': 'OK', 'detail': 'Service actif'})
            else:
                findings.append({'check': 'Firewall UFW', 'status': 'CRITIQUE', 'detail': 'Service inactif'})
        except Exception as e:
            findings.append({'check': 'Firewall', 'status': 'CRITIQUE', 'detail': f'Non detecte: {e}'})
    return findings


def check_fail2ban():
    """Check fail2ban status"""
    findings = []
    try:
        result = subprocess.run(['systemctl', 'is-active', 'fail2ban'], capture_output=True, text=True, timeout=5)
        if result.stdout.strip() == 'active':
            findings.append({'check': 'Fail2ban', 'status': 'OK', 'detail': 'Actif'})
            # Check jails
            try:
                r = subprocess.run(['sudo', '-n', 'fail2ban-client', 'status'],
                                   capture_output=True, text=True, timeout=10)
                if r.returncode == 0:
                    jail_match = re.search(r'Jail list:\s*(.*)', r.stdout)
                    if jail_match:
                        findings[-1]['detail'] = f"Actif - Jails: {jail_match.group(1).strip()}"
            except Exception:
                pass
        else:
            findings.append({'check': 'Fail2ban', 'status': 'CRITIQUE', 'detail': 'Non installe ou inactif'})
    except Exception:
        findings.append({'check': 'Fail2ban', 'status': 'CRITIQUE', 'detail': 'Non installe'})
    return findings


def check_auto_updates():
    """Check if unattended-upgrades is configured"""
    findings = []
    try:
        result = subprocess.run(['dpkg', '-l', 'unattended-upgrades'],
                                capture_output=True, text=True, timeout=10)
        if 'ii' in result.stdout:
            findings.append({'check': 'Mises a jour auto', 'status': 'OK', 'detail': 'unattended-upgrades installe'})
        else:
            findings.append({'check': 'Mises a jour auto', 'status': 'CRITIQUE',
                             'detail': 'unattended-upgrades non installe'})
    except Exception:
        findings.append({'check': 'Mises a jour auto', 'status': 'CRITIQUE', 'detail': 'Verification impossible'})
    return findings


def check_sudo_config():
    """Check sudo configuration"""
    findings = []
    try:
        result = subprocess.run(['sudo', '-n', 'cat', '/etc/sudoers.d/michel'],
                                capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            content = result.stdout.strip()
            if 'NOPASSWD' in content and 'ALL' in content:
                # Check if it's unrestricted NOPASSWD:ALL or limited
                if re.search(r'NOPASSWD:\s*ALL\s*$', content, re.MULTILINE):
                    findings.append({'check': 'Sudo NOPASSWD', 'status': 'CRITIQUE',
                                     'detail': 'NOPASSWD:ALL sans restriction'})
                else:
                    findings.append({'check': 'Sudo NOPASSWD', 'status': 'MOYENNE',
                                     'detail': 'NOPASSWD limite a certaines commandes'})
            elif 'NOPASSWD' not in content:
                findings.append({'check': 'Sudo NOPASSWD', 'status': 'OK',
                                 'detail': 'Pas de NOPASSWD'})
            else:
                findings.append({'check': 'Sudo config', 'status': 'OK', 'detail': content[:80]})
        else:
            # Can't read — try to infer from sudo -n behavior
            r2 = subprocess.run(['sudo', '-n', 'true'], capture_output=True, timeout=5)
            if r2.returncode == 0:
                findings.append({'check': 'Sudo NOPASSWD', 'status': 'CRITIQUE',
                                 'detail': 'sudo sans mot de passe fonctionne'})
            else:
                findings.append({'check': 'Sudo NOPASSWD', 'status': 'OK',
                                 'detail': 'sudo requiert un mot de passe'})
    except Exception:
        findings.append({'check': 'Sudo config', 'status': 'FAIBLE', 'detail': 'Verification impossible'})
    return findings


def check_ssh_keys():
    """Check SSH key permissions"""
    findings = []
    ssh_dir = Path.home() / '.ssh'
    if ssh_dir.exists():
        for f in ssh_dir.iterdir():
            if f.is_file() and not f.name.endswith('.pub') and f.name not in ('known_hosts', 'known_hosts.old', 'authorized_keys', 'config'):
                mode = oct(f.stat().st_mode)[-3:]
                if mode != '600':
                    findings.append({'check': f'SSH key {f.name}', 'status': 'HAUTE',
                                     'detail': f'Permissions {mode} (devrait etre 600)'})
                else:
                    findings.append({'check': f'SSH key {f.name}', 'status': 'OK',
                                     'detail': 'Permissions 600'})
    if not findings:
        findings.append({'check': 'SSH keys', 'status': 'OK', 'detail': 'Aucune cle privee ou permissions OK'})
    return findings


def check_ssh_tunnel_service():
    """Check SSH tunnel security"""
    findings = []
    service_path = Path('/etc/systemd/system/ssh-tunnel.service')
    if service_path.exists():
        try:
            content = service_path.read_text()
            if 'StrictHostKeyChecking=no' in content:
                findings.append({'check': 'SSH tunnel StrictHostKeyChecking', 'status': 'CRITIQUE',
                                 'detail': 'StrictHostKeyChecking=no (vulnerable MITM)'})
            elif 'StrictHostKeyChecking=accept-new' in content:
                findings.append({'check': 'SSH tunnel StrictHostKeyChecking', 'status': 'OK',
                                 'detail': 'accept-new (securise)'})
            else:
                findings.append({'check': 'SSH tunnel StrictHostKeyChecking', 'status': 'OK',
                                 'detail': 'Configuration correcte'})
        except PermissionError:
            findings.append({'check': 'SSH tunnel', 'status': 'FAIBLE', 'detail': 'Impossible de lire le service'})
    return findings


def check_pending_updates():
    """Check for available security updates"""
    findings = []
    try:
        result = subprocess.run(['apt', 'list', '--upgradable'],
                                capture_output=True, text=True, timeout=30)
        upgradable = [l for l in result.stdout.splitlines() if l and not l.startswith('Listing')]
        security_updates = [l for l in upgradable if 'security' in l.lower()]

        if security_updates:
            findings.append({'check': 'Mises a jour securite', 'status': 'HAUTE',
                             'detail': f'{len(security_updates)} mises a jour de securite en attente'})
        elif upgradable:
            findings.append({'check': 'Mises a jour', 'status': 'FAIBLE',
                             'detail': f'{len(upgradable)} paquets a mettre a jour'})
        else:
            findings.append({'check': 'Mises a jour', 'status': 'OK', 'detail': 'Systeme a jour'})
    except Exception:
        findings.append({'check': 'Mises a jour', 'status': 'FAIBLE', 'detail': 'Verification impossible'})
    return findings


# --- Remote checks ---

def check_ssl_cert(hostname):
    """Check SSL certificate validity and expiration"""
    findings = []
    try:
        context = ssl.create_default_context()
        with socket.create_connection((hostname, 443), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()

                # Expiration
                not_after_str = cert.get('notAfter', '')
                not_after = datetime.strptime(not_after_str, '%b %d %H:%M:%S %Y %Z').replace(tzinfo=timezone.utc)
                days_left = (not_after - datetime.now(timezone.utc)).days

                # Issuer
                issuer = dict(x[0] for x in cert.get('issuer', []))
                issuer_cn = issuer.get('commonName', 'Unknown')

                # Subject
                subject = dict(x[0] for x in cert.get('subject', []))
                subject_cn = subject.get('commonName', 'Unknown')

                # TLS version
                tls_version = ssock.version()

                if days_left < 7:
                    severity = 'CRITIQUE'
                elif days_left < 14:
                    severity = 'HAUTE'
                elif days_left < 30:
                    severity = 'MOYENNE'
                else:
                    severity = 'OK'

                findings.append({
                    'check': f'Certificat {hostname}',
                    'status': severity,
                    'detail': f'{days_left}j restants (expire {not_after.strftime("%d/%m/%Y")})',
                    'issuer': issuer_cn,
                    'subject': subject_cn,
                    'tls': tls_version,
                    'days_left': days_left
                })

    except ssl.SSLCertVerificationError as e:
        findings.append({'check': f'Certificat {hostname}', 'status': 'CRITIQUE',
                         'detail': f'Certificat invalide: {e}'})
    except Exception as e:
        findings.append({'check': f'Certificat {hostname}', 'status': 'HAUTE',
                         'detail': f'Erreur connexion: {e}'})
    return findings


def check_tls_versions(hostname):
    """Check that old TLS versions are rejected"""
    findings = []
    for version_name, method_name in [('TLS 1.0', 'TLSv1'), ('TLS 1.1', 'TLSv1_1')]:
        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            ctx.maximum_version = getattr(ssl.TLSVersion, method_name, None)
            if ctx.maximum_version is None:
                findings.append({'check': f'{hostname} {version_name}', 'status': 'OK',
                                 'detail': f'{version_name} non supporte par le client (OK)'})
                continue
            ctx.minimum_version = ctx.maximum_version
            with socket.create_connection((hostname, 443), timeout=5) as sock:
                ctx.wrap_socket(sock, server_hostname=hostname)
                # If we get here, the old version is accepted
                findings.append({'check': f'{hostname} {version_name}', 'status': 'HAUTE',
                                 'detail': f'{version_name} accepte (devrait etre refuse)'})
        except (ssl.SSLError, OSError):
            findings.append({'check': f'{hostname} {version_name}', 'status': 'OK',
                             'detail': f'{version_name} refuse'})
        except Exception:
            findings.append({'check': f'{hostname} {version_name}', 'status': 'OK',
                             'detail': f'{version_name} non disponible'})
    return findings


def check_http_headers(hostname):
    """Check security headers"""
    findings = []
    url = f'https://{hostname}'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Michel-SecurityAudit/1.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            headers = {k.lower(): v for k, v in response.headers.items()}
    except urllib.error.HTTPError as e:
        headers = {k.lower(): v for k, v in e.headers.items()}
    except Exception as e:
        findings.append({'check': f'Headers {hostname}', 'status': 'HAUTE', 'detail': f'Erreur: {e}'})
        return findings

    # Check required headers
    missing = []
    present = []
    for h in REQUIRED_HEADERS:
        if h in headers:
            present.append(h)
        else:
            missing.append(h)

    if missing:
        findings.append({'check': f'Headers {hostname}', 'status': 'HAUTE',
                         'detail': f'Manquants: {", ".join(missing)}'})
    else:
        findings.append({'check': f'Headers {hostname}', 'status': 'OK',
                         'detail': f'Tous presents ({len(present)}/{len(REQUIRED_HEADERS)})'})

    # Check CSP
    if 'content-security-policy' not in headers:
        findings.append({'check': f'CSP {hostname}', 'status': 'MOYENNE',
                         'detail': 'Pas de Content-Security-Policy'})

    return findings


def check_open_ports_remote(server_name, host, ports):
    """Scan ports on remote server"""
    findings = []
    open_ports = []
    for port in ports:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                open_ports.append(str(port))
        except Exception:
            pass

    unexpected = [p for p in open_ports if p not in ('22', '80', '443', '2111')]
    if unexpected:
        findings.append({'check': f'Ports {server_name}', 'status': 'HAUTE',
                         'detail': f'Ports ouverts: {", ".join(open_ports)} (inattendus: {", ".join(unexpected)})'})
    else:
        findings.append({'check': f'Ports {server_name}', 'status': 'OK',
                         'detail': f'Ports ouverts: {", ".join(open_ports)}'})
    return findings


def check_ssh_banner(host):
    """Get SSH banner to check version"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((host, 22))
        banner = sock.recv(256).decode('utf-8', errors='ignore').strip()
        sock.close()

        # Parse version
        version_match = re.search(r'OpenSSH[_\s](\d+\.\d+)', banner)
        if version_match:
            version = float(version_match.group(1))
            if version < 8.5:
                return {'check': f'SSH {host}', 'status': 'HAUTE',
                        'detail': f'{banner} (obsolete, < 8.5)'}
            elif version < 9.0:
                return {'check': f'SSH {host}', 'status': 'MOYENNE',
                        'detail': f'{banner} (vieillissant)'}
            else:
                return {'check': f'SSH {host}', 'status': 'OK', 'detail': banner}
        return {'check': f'SSH {host}', 'status': 'FAIBLE', 'detail': f'Banner: {banner}'}
    except Exception:
        return {'check': f'SSH {host}', 'status': 'OK', 'detail': 'Port 22 ferme ou timeout'}


# --- Report generation ---

def severity_icon(status):
    """Return emoji for severity level"""
    icons = {
        'CRITIQUE': '🔴',
        'HAUTE': '🟠',
        'MOYENNE': '🟡',
        'FAIBLE': '🔵',
        'OK': '✅'
    }
    return icons.get(status, '⚪')


def calculate_score(findings):
    """Calculate security score out of 100"""
    total_checks = len(findings)
    if total_checks == 0:
        return 100

    deductions = sum(SEVERITY_WEIGHT.get(f['status'], 0) for f in findings)
    max_deduction = total_checks * SEVERITY_WEIGHT['CRITIQUE']
    score = max(0, round(100 - (deductions / max_deduction * 100)))
    return score


def generate_report(local_findings, remote_findings, score):
    """Generate human-readable report text"""
    now = datetime.now().strftime('%d/%m/%Y %H:%M')
    lines = [f"🔒 Audit de securite — {now}", ""]

    # Score
    if score >= 80:
        score_icon = "🟢"
    elif score >= 60:
        score_icon = "🟡"
    else:
        score_icon = "🔴"
    lines.append(f"Score global: {score_icon} {score}/100")
    lines.append("")

    # Summary counts
    all_findings = local_findings + remote_findings
    counts = {}
    for f in all_findings:
        s = f['status']
        counts[s] = counts.get(s, 0) + 1

    summary_parts = []
    for sev in ['CRITIQUE', 'HAUTE', 'MOYENNE', 'FAIBLE', 'OK']:
        if counts.get(sev, 0) > 0:
            summary_parts.append(f"{severity_icon(sev)} {counts[sev]} {sev}")
    lines.append(" | ".join(summary_parts))
    lines.append("")

    # Local findings
    if local_findings:
        lines.append("🖥 GK41 (Local)")
        problems = [f for f in local_findings if f['status'] != 'OK']
        ok_count = len(local_findings) - len(problems)

        for f in problems:
            lines.append(f"  {severity_icon(f['status'])} {f['check']}: {f['detail']}")
        if ok_count > 0:
            lines.append(f"  ✅ {ok_count} checks OK")
        lines.append("")

    # Remote findings
    if remote_findings:
        lines.append("🌐 Serveurs distants")
        problems = [f for f in remote_findings if f['status'] != 'OK']
        ok_count = len(remote_findings) - len(problems)

        for f in problems:
            lines.append(f"  {severity_icon(f['status'])} {f['check']}: {f['detail']}")
        if ok_count > 0:
            lines.append(f"  ✅ {ok_count} checks OK")
        lines.append("")

    # Recommendations
    critical = [f for f in all_findings if f['status'] == 'CRITIQUE']
    high = [f for f in all_findings if f['status'] == 'HAUTE']
    if critical or high:
        lines.append("⚡ Actions recommandees")
        for f in critical:
            lines.append(f"  🔴 {f['check']}: {f['detail']}")
        for f in high:
            lines.append(f"  🟠 {f['check']}: {f['detail']}")

    return "\n".join(lines)


# --- Commands ---

def cmd_audit(args):
    """Full security audit"""
    local_findings = []
    remote_findings = []

    if not args.remote:
        # Local checks
        logger.info("Running local security checks...")
        local_findings.extend(check_ssh_config())
        local_findings.extend(check_firewall())
        local_findings.extend(check_fail2ban())
        local_findings.extend(check_auto_updates())
        local_findings.extend(check_sudo_config())
        local_findings.extend(check_ssh_keys())
        local_findings.extend(check_ssh_tunnel_service())
        local_findings.extend(check_open_ports())
        local_findings.extend(check_pending_updates())

    if not args.local:
        # Remote checks
        logger.info("Running remote security checks...")

        # SSL certificates
        for hostname in HTTPS_SERVERS:
            remote_findings.extend(check_ssl_cert(hostname))

        # TLS versions
        for hostname in HTTPS_SERVERS:
            remote_findings.extend(check_tls_versions(hostname))

        # HTTP headers
        for hostname in HTTPS_SERVERS:
            remote_findings.extend(check_http_headers(hostname))

        # Port scan
        for server_name, info in ALL_SERVERS.items():
            remote_findings.extend(check_open_ports_remote(server_name, info['host'], info['ports']))

        # SSH banners
        for server_name, info in ALL_SERVERS.items():
            if 22 in info['ports']:
                remote_findings.append(check_ssh_banner(info['host']))

    # Calculate score
    all_findings = local_findings + remote_findings
    score = calculate_score(all_findings)

    # Generate report
    report = generate_report(local_findings, remote_findings, score)

    # Output
    result = {
        'success': True,
        'timestamp': datetime.now().isoformat(),
        'score': score,
        'local_findings': local_findings,
        'remote_findings': remote_findings,
        'total_checks': len(all_findings),
        'summary': {s: sum(1 for f in all_findings if f['status'] == s)
                    for s in ['CRITIQUE', 'HAUTE', 'MOYENNE', 'FAIBLE', 'OK']}
    }

    # Save history
    append_history(result)

    if args.send:
        send_alert(report)

    print(report)
    print("\n---")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_certs(args):
    """Check SSL certificates only"""
    findings = []
    for hostname in HTTPS_SERVERS:
        findings.extend(check_ssl_cert(hostname))

    now = datetime.now().strftime('%d/%m/%Y %H:%M')
    lines = [f"🔐 Certificats SSL — {now}", ""]
    for f in findings:
        lines.append(f"  {severity_icon(f['status'])} {f['check']}: {f['detail']}")
        if 'issuer' in f:
            lines.append(f"      Emetteur: {f['issuer']} | TLS: {f.get('tls', '?')}")
    report = "\n".join(lines)

    if args.send:
        send_alert(report)

    print(report)

    # Alert if any cert expires in < 14 days
    urgent = [f for f in findings if f.get('days_left', 999) < 14]
    if urgent:
        for f in urgent:
            send_alert(f"🚨 URGENT: {f['check']} expire dans {f['days_left']} jours !")
        return 1
    return 0


def cmd_fixes(args):
    """Show recommended fixes as a shell script"""
    script = """#!/bin/bash
# Security fixes for GK41 - AVS Technologies
# Generated by brain_security_audit.py
# Run with: sudo bash security_fixes.sh

set -e

echo "🔒 Application des corrections de securite..."

# 1. Restreindre sudo NOPASSWD
echo "[1/6] Restriction sudo NOPASSWD..."
cat > /etc/sudoers.d/michel << 'SUDOERS'
# Michel: NOPASSWD limit to essential commands
michel ALL=(ALL) NOPASSWD: /bin/systemctl, /usr/bin/systemctl, /usr/bin/apt, /usr/bin/apt-get, /usr/bin/journalctl, /usr/bin/python3, /usr/bin/fail2ban-client, /usr/bin/unattended-upgrades, /usr/sbin/ufw
# Require password for everything else
michel ALL=(ALL:ALL) ALL
SUDOERS
chmod 440 /etc/sudoers.d/michel
visudo -c && echo "  ✅ sudoers OK" || { echo "  ❌ sudoers INVALIDE"; exit 1; }

# 2. Fix SSH tunnel StrictHostKeyChecking
echo "[2/6] Fix SSH tunnel..."
if [ -f /etc/systemd/system/ssh-tunnel.service ]; then
    sed -i 's/StrictHostKeyChecking=no/StrictHostKeyChecking=accept-new/' /etc/systemd/system/ssh-tunnel.service
    systemctl daemon-reload
    systemctl restart ssh-tunnel
    echo "  ✅ SSH tunnel corrige"
else
    echo "  ⚠️ ssh-tunnel.service non trouve"
fi

# 3. Disable X11Forwarding
echo "[3/6] Desactivation X11Forwarding..."
sed -i 's/^X11Forwarding yes/X11Forwarding no/' /etc/ssh/sshd_config
systemctl reload sshd
echo "  ✅ X11Forwarding desactive"

# 4. Install and configure fail2ban
echo "[4/6] Installation fail2ban..."
apt install -y fail2ban
cat > /etc/fail2ban/jail.local << 'F2B'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true
port = 7912
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
F2B
systemctl enable fail2ban
systemctl restart fail2ban
echo "  ✅ fail2ban configure (port 7912)"

# 5. Install unattended-upgrades
echo "[5/6] Installation mises a jour auto..."
apt install -y unattended-upgrades apt-listchanges
cat > /etc/apt/apt.conf.d/20auto-upgrades << 'UU'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
UU
echo "  ✅ unattended-upgrades configure"

# 6. Install audit tools
echo "[6/6] Installation outils audit..."
apt install -y nmap ssh-audit lynis
echo "  ✅ Outils installes"

echo ""
echo "🎉 Corrections appliquees ! Relancez l'audit pour verifier."
echo "   python3 brain_security_audit.py audit"
"""
    print(script)
    return 0


def main():
    parser = argparse.ArgumentParser(description='Brain Security Audit')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # audit
    p_audit = subparsers.add_parser('audit', help='Full security audit')
    p_audit.add_argument('--local', action='store_true', help='Local checks only')
    p_audit.add_argument('--remote', action='store_true', help='Remote checks only')
    p_audit.add_argument('--send', action='store_true', help='Send report via Telegram')

    # certs
    p_certs = subparsers.add_parser('certs', help='Check SSL certificates')
    p_certs.add_argument('--send', action='store_true', help='Send report via Telegram')

    # fixes
    subparsers.add_parser('fixes', help='Generate fix script')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        'audit': cmd_audit,
        'certs': cmd_certs,
        'fixes': cmd_fixes,
    }

    return commands[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
