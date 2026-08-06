---
title: Ransomware Prevention and Response (CISA #StopRansomware)
keywords: ransomware, cisa, stopransomware, malware, backups, 3-2-1, extortion, double extortion, encryption, ransom payment, patching, rdp, phishing, incident response, fbi, ic3, ms-isac, recovery
---

# Ransomware Prevention and Response (CISA #StopRansomware)

## Key facts
- Ransomware is malware that encrypts your files and systems, with criminals demanding payment for decryption (CISA).
- "Double extortion" is now standard: attackers also steal data and threaten to leak it if you don't pay (CISA).
- FBI and CISA do NOT encourage paying ransom — payment doesn't guarantee recovery and funds further crime.
- Some victims pay and still never get their files back — there is no guarantee (CISA StopRansomware FAQ).
- Top infection routes: phishing emails, compromised credentials/RDP, and unpatched internet-facing software (CISA guide).
- The FBI's IC3 received 3,611 ransomware complaints in 2025, with reported losses exceeding $32 million.
- Ransomware losses are understated: IC3 figures exclude downtime, lost business, and recovery costs.
- Over 1,400 of 2025's ransomware complaints came from critical infrastructure organizations (IC3).
- Follow the 3-2-1 backup rule: 3 copies of important files, on 2 different media, with 1 stored offsite (CISA).
- Keep backups offline and encrypted — many ransomware strains hunt down and delete reachable backups (CISA).
- Test your backups regularly; an untested backup is a hope, not a plan (CISA guide).
- Patch promptly, prioritizing internet-facing systems and known exploited vulnerabilities (CISA).
- Use phishing-resistant MFA on all services — especially email, VPNs and remote access (CISA guide).
- Audit and close unused RDP ports, enforce account lockouts, and log RDP login attempts (CISA guide).
- The #StopRansomware Guide is joint guidance from CISA, MS-ISAC, NSA and FBI (updated May 2023).

## How ransomware spreads
- Phishing emails with malicious links or attachments.
- Stolen or brute-forced credentials, especially exposed Remote Desktop Protocol (RDP).
- Exploitation of unpatched software vulnerabilities on internet-facing servers.
- "Dropper" malware (e.g. QakBot, Emotet) that sells access to your network to ransomware operators.

## Prevention checklist (from the #StopRansomware Guide)
- Maintain offline, encrypted backups of critical data and test restoration regularly.
- Keep a printed, offline copy of your incident response plan.
- Patch and update software and operating systems — fastest for internet-facing systems.
- Require MFA everywhere, preferring phishing-resistant methods.
- Segment networks to stop ransomware from spreading between systems.
- Train staff to recognize and report phishing — the top initial access vector.
- Implement email authentication (DMARC, SPF, DKIM) to reduce spoofed mail.

## If you're hit — do and don't
- DO disconnect infected devices from the network (unplug ethernet, drop Wi-Fi) to contain spread.
- DO consult law enforcement before acting — free decryptors exist for some variants.
- DO restore from clean offline backups only after the environment is fully cleaned and patched.
- DON'T pay the ransom: FBI/CISA warn it doesn't guarantee your files and emboldens attackers.
- DON'T wipe systems before capturing images/logs — evidence helps investigators and your recovery.
- DON'T assume it's over after decryption — hunt for the persistence mechanisms attackers left behind.

## Poster-ready reminders
- Backups are your best ransom note response: 3 copies, 2 media, 1 offsite.
- Patch today — ransomware loves yesterday's vulnerabilities.
- One phishing click can encrypt an entire network: pause before you click.
- Paying the ransom funds the next attack — and may not get your data back.

## Reporting
- Report to CISA: cisa.gov/report, report@cisa.gov, or call 1-844-SAY-CISA (1-844-729-2472).
- Report to the FBI: your local field office or the Internet Crime Complaint Center at ic3.gov.
- US state/local/tribal/territorial orgs can also contact MS-ISAC: soc@msisac.org or (866) 787-4722.

## Sources
- CISA — #StopRansomware Guide (CISA/MS-ISAC/NSA/FBI) — https://www.cisa.gov/stopransomware/ransomware-guide
- CISA — StopRansomware portal and FAQs — https://www.cisa.gov/stopransomware
- FBI IC3 — 2025 Internet Crime Report (ransomware section) — https://www.ic3.gov/AnnualReport/Reports/2025_IC3Report.pdf
- CISA — Data Backup Options (3-2-1 rule) — https://www.cisa.gov/sites/default/files/publications/data_backup_options.pdf
