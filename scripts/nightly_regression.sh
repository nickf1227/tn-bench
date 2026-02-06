#!/bin/bash
# TN-Bench Automated Regression Test Script
# Runs nightly to check for new commits and execute tests

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="/Users/nickf/.openclaw/workspace/Projects/TN-Bench"
LOG_DIR="${WORKSPACE}/logs"
AUDIT_LOG="${LOG_DIR}/audit.log"
TEST_BOX="root@10.69.10.119"
TEST_BOX_PASSWORD="abcd1234"
REPO_DIR="/root/tn-bench"
TIMESTAMP=$(date '+%Y-%m-%d_%H-%M-%S')
DATE=$(date '+%Y-%m-%d')

# Ensure log directory exists
mkdir -p "${LOG_DIR}"

# Logging functions
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "${AUDIT_LOG}"
}

log_audit() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [AUDIT] $1" >> "${AUDIT_LOG}"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $1" | tee -a "${AUDIT_LOG}"
}

# SSH to test box with audit logging
ssh_test_box() {
    local cmd="$1"
    log_audit "SSH COMMAND: ${cmd}"
    sshpass -p "${TEST_BOX_PASSWORD}" ssh -o StrictHostKeyChecking=no -o LogLevel=ERROR "${TEST_BOX}" "${cmd}" 2>&1
}

# Main test execution
main() {
    log "Starting TN-Bench regression test check"
    
    # Check connectivity to test box
    if ! ssh_test_box "echo 'connected'" > /dev/null 2>&1; then
        log_error "Failed to connect to test box ${TEST_BOX}"
        exit 1
    fi
    log "Test box connectivity verified"
    
    # Check current local commit
    cd "${WORKSPACE}/tn-bench"
    LOCAL_COMMIT=$(git rev-parse HEAD)
    LOCAL_BRANCH=$(git rev-parse --abbrev-ref HEAD)
    log "Local branch: ${LOCAL_BRANCH}, commit: ${LOCAL_COMMIT:0:8}"
    
    # Fetch latest from remote
    git fetch origin
    REMOTE_COMMIT=$(git rev-parse origin/${LOCAL_BRANCH})
    
    if [ "${LOCAL_COMMIT}" = "${REMOTE_COMMIT}" ]; then
        log "No new commits on ${LOCAL_BRANCH}. Skipping test."
        exit 0
    fi
    
    log "New commits detected!"
    log "Remote commit: ${REMOTE_COMMIT:0:8}"
    
    # Get commit message for audit
    COMMIT_MSG=$(git log --oneline -1 "${REMOTE_COMMIT}")
    log_audit "NEW COMMIT: ${COMMIT_MSG}"
    
    # Update local repo
    log "Pulling latest changes..."
    git pull origin "${LOCAL_BRANCH}"
    log_audit "LOCAL PULL: ${LOCAL_BRANCH}"
    
    # Update test box
    log "Updating test box repository..."
    ssh_test_box "cd ${REPO_DIR} && git fetch origin && git reset --hard origin/${LOCAL_BRANCH}"
    log_audit "TEST BOX UPDATE: ${LOCAL_BRANCH} reset to ${REMOTE_COMMIT:0:8}"
    
    # Run TN-Bench with automated inputs
    log "Starting TN-Bench test execution..."
    
    TEST_OUTPUT="${LOG_DIR}/test_${TIMESTAMP}.log"
    
    # Run test with expect-like behavior using printf
    ssh_test_box "
        cd ${REPO_DIR}
        printf 'yes\n1\n1\n1\n' | python3 truenas-bench.py 2>&1
    " > "${TEST_OUTPUT}"
    
    TEST_EXIT_CODE=$?
    log_audit "TEST EXECUTION: Exit code ${TEST_EXIT_CODE}"
    
    if [ ${TEST_EXIT_CODE} -eq 0 ]; then
        log "TEST PASSED: Output saved to ${TEST_OUTPUT}"
        
        # Check if JSON results were created
        JSON_FILE=$(ssh_test_box "ls -t ${REPO_DIR}/tn_bench_results.json 2>/dev/null | head -1")
        if [ -n "${JSON_FILE}" ]; then
            log "JSON results generated: ${JSON_FILE}"
            ssh_test_box "cat ${JSON_FILE}" > "${LOG_DIR}/results_${TIMESTAMP}.json"
            log_audit "RESULTS SAVED: ${LOG_DIR}/results_${TIMESTAMP}.json"
        fi
        
        # Cleanup test dataset
        log "Cleaning up test dataset..."
        ssh_test_box "zfs destroy tnbench/tn-bench 2>/dev/null || true"
        log_audit "DATASET CLEANUP: tnbench/tn-bench destroyed"
    else
        log_error "TEST FAILED: Exit code ${TEST_EXIT_CODE}"
        log_error "Output: ${TEST_OUTPUT}"
    fi
    
    # Summary
    log "Regression test check complete"
    log "========================================"
    log "Test Date: ${DATE}"
    log "Commit: ${REMOTE_COMMIT:0:8}"
    log "Branch: ${LOCAL_BRANCH}"
    log "Result: $([ ${TEST_EXIT_CODE} -eq 0 ] && echo 'PASSED' || echo 'FAILED')"
    log "========================================"
}

# Run main
main "$@"
