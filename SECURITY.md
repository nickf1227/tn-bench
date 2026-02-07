# tn-bench Security & Change Control Guidelines

## Overview
This document outlines security best practices and change control procedures for tn-bench development and testing.

## Audit Logging

### Location
All audit logs are stored in: `/Users/nickf/.openclaw/workspace/Projects/tn-bench/logs/`

### Log Files
- **audit.log**: Commands executed on test box (SSH commands)
- **test_*.log**: Individual test run outputs
- **results_*.json**: JSON benchmark results from test runs

### Log Format
```
[YYYY-MM-DD HH:MM:SS] [AUDIT] SSH COMMAND: <command>
[YYYY-MM-DD HH:MM:SS] [AUDIT] NEW COMMIT: <commit_hash> <message>
[YYYY-MM-DD HH:MM:SS] [AUDIT] TEST EXECUTION: Exit code <code>
[YYYY-MM-DD HH:MM:SS] [AUDIT] RESULTS SAVED: <path>
```

## Automated Testing (Nightly Regression)

### Schedule
- **Frequency**: Daily at 2:00 AM EST
- **Trigger**: Cron job ID `b5d92b7e-4830-485d-8967-b21758e5195e`
- **Script**: `scripts/nightly_regression.sh`

### Process Flow
1. Check connectivity to test box (10.69.10.119)
2. Compare local commit with remote (tn-bench-2.0 branch)
3. If new commits exist:
   - Log commit hash and message
   - Pull changes locally
   - Update test box repository
   - Execute tn-bench with automated inputs
   - Capture results
   - Cleanup test datasets
   - Log completion status

### Automated Test Inputs
- Confirmation: `yes`
- Pool selection: `1` (tnbench pool)
- ZFS iterations: `1` (quick test)
- Disk iterations: `1` (quick test)

## Security Best Practices

### 1. Test Box Access Control
**Current**: Password-based SSH (abcd1234)

**Recommended Improvements**:
```bash
# Option A: SSH Key-based Authentication (Preferred)
# Generate key pair locally
ssh-keygen -t ed25519 -f ~/.ssh/tn_bench_test -C "tn-bench-testing"

# Copy public key to test box
ssh-copy-id -i ~/.ssh/tn_bench_test.pub root@10.69.10.119

# Update scripts to use key
ssh -i ~/.ssh/tn_bench_test root@10.69.10.119
```

**Benefits**:
- No passwords in scripts/logs
- Revocable access (delete key from authorized_keys)
- Audit trail of key usage

### 2. Credential Management
**Current State**: Password stored in plaintext in script

**Recommended**:
- Use SSH keys (see above)
- Or use environment variables:
  ```bash
  export TN_BENCH_TEST_PASSWORD="$(security find-generic-password -s tn-bench-test -w)"
  ```
- Or use macOS Keychain to store password securely

### 3. Test Box Hardening
**Recommendations**:
- Create dedicated `tnbench` user instead of root:
  ```bash
  pw user add tnbench -m
  # Add to wheel group for sudo
  pw groupmod wheel -m tnbench
  ```
- Limit SSH to key auth only:
  ```bash
  # /etc/ssh/sshd_config
  PasswordAuthentication no
  PermitRootLogin no
  AllowUsers tnbench
  ```
- Restrict to specific commands via `authorized_keys`:
  ```
  command="/usr/local/bin/tn-bench-wrapper",no-port-forwarding,no-X11-forwarding ssh-ed25519 AAA...
  ```

### 4. Network Security
**Current**: SSH on default port (likely 22)

**Recommendations**:
- Consider non-standard SSH port:
  ```bash
  # /etc/ssh/sshd_config
  Port 2222
  ```
- Firewall rules limiting access:
  ```bash
  # Only allow from OpenClaw host IP
  pfctl -t allowed_hosts -T add <openclaw_host_ip>
  ```

### 5. Change Control Process

#### Before Merging Changes
1. **Code Review**: All changes must be reviewed before merge
2. **Local Testing**: Run basic functionality tests locally
3. **Branch Protection**: Protect `main` and `tn-bench-2.0` branches
4. **Commit Signing**: Consider GPG signing commits:
   ```bash
   git config commit.gpgsign true
   git config user.signingkey <key_id>
   ```

#### Release Process
1. Tag releases:
   ```bash
   git tag -a v2.0.1 -m "Release v2.0.1 - Fixed JSON output"
   git push origin v2.0.1
   ```
2. Document changes in CHANGELOG.md
3. Update README with any breaking changes

### 6. Audit Trail Requirements
**Mandatory Logging**:
- ✅ Who made the change (git commit author)
- ✅ When (timestamp)
- ✅ What was changed (commit diff)
- ✅ Test results (pass/fail with output)
- ✅ Commands executed on test infrastructure

**Retention**:
- Keep logs for 90 days minimum
- Archive JSON results indefinitely for trend analysis

### 7. Incident Response
**If Test Box is Compromised**:
1. Immediately revoke SSH access (remove key from authorized_keys)
2. Check audit logs for unauthorized commands
3. Rebuild test box from known-good snapshot
4. Review recent commits for malicious code
5. Rotate all credentials

**If Malicious Code Detected**:
1. Quarantine the commit (revert immediately)
2. Audit all systems that ran the code
3. Check for data exfiltration
4. Post-incident review

### 8. Data Protection
**Test Data**:
- tn-bench uses synthetic data (`/dev/urandom`)
- No real user data is processed
- Safe to run on test infrastructure

**Results Data**:
- JSON results contain system specs and performance metrics
- No sensitive data (passwords, keys, user data)
- Safe to store in logs

## Current Risk Assessment

| Risk | Level | Mitigation |
|------|-------|------------|
| Password in plaintext | 🔴 High | Switch to SSH keys |
| Root access on test box | 🟡 Medium | Create dedicated user |
| No commit signing | 🟡 Medium | Enable GPG signing |
| Test box on same network | 🟢 Low | Acceptable for testing |
| No command restrictions | 🟡 Medium | Implement forced commands |

## Recommended Action Plan

### Phase 1: Immediate (This Week)
1. ✅ Set up audit logging (DONE)
2. ✅ Set up nightly regression cron (DONE)
3. Switch to SSH key authentication

### Phase 2: Short-term (Next 2 Weeks)
1. Create dedicated `tnbench` user on test box
2. Restrict SSH to key-only auth
3. Enable branch protection on GitHub

### Phase 3: Ongoing
1. Weekly review of audit logs
2. Monthly security assessment
3. Quarterly access review

## Tools & Commands

### Check Audit Logs
```bash
# View recent audit entries
tail -f /Users/nickf/.openclaw/workspace/Projects/tn-bench/logs/audit.log

# Search for specific commands
grep "SSH COMMAND" audit.log | grep "zfs destroy"

# View test results
ls -lt /Users/nickf/.openclaw/workspace/Projects/tn-bench/logs/test_*.log
```

### Manual Test Trigger
```bash
# Run regression test manually
/Users/nickf/.openclaw/workspace/Projects/tn-bench/scripts/nightly_regression.sh
```

### Check Cron Status
```bash
# View scheduled jobs
openclaw cron list

# Check next run time
openclaw cron status
```

## Questions?

Contact: Nick (maintainer)
