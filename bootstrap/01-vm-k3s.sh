#!/usr/bin/env bash
# Phase 1 부트스트랩: OrbStack VM + k3s (ADR-0009 실험 플레인)
# idempotent — 재실행해도 안전.
set -euo pipefail

VM_NAME="mlx-1"
K3S_VERSION="v1.32.13+k3s1"
KUBECONFIG_PATH="${HOME}/.kube/aporiax-lab.yaml"
CONTEXT_NAME="aporiax-lab"

log() {
  echo "[bootstrap] $*"
}

# 1. VM 존재 확인, 없으면 생성
log "VM 존재 확인 중: ${VM_NAME}"
if orb list | grep -q "${VM_NAME}"; then
  log "VM ${VM_NAME} 이미 존재함 — 생성 스킵"
else
  log "VM ${VM_NAME} 생성 중 (ubuntu)"
  orb create ubuntu "${VM_NAME}"
fi

# 2. k3s 설치 확인, 없으면 설치
log "k3s 설치 확인 중"
if orb -m "${VM_NAME}" sh -c "command -v k3s" >/dev/null 2>&1; then
  log "k3s 이미 설치됨 — 설치 스킵"
else
  log "k3s 설치 중 (${K3S_VERSION})"
  orb -m "${VM_NAME}" sudo sh -c "curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC='server' INSTALL_K3S_VERSION='${K3S_VERSION}' sh -"
fi

# 3. kubeconfig 추출 + 치환
log "VM IP 조회 중"
VM_IP="$(orb -m "${VM_NAME}" hostname -I | awk '{print $1}')"
log "VM IP: ${VM_IP}"

log "kubeconfig 추출 및 치환 중 → ${KUBECONFIG_PATH}"
mkdir -p "$(dirname "${KUBECONFIG_PATH}")"
orb -m "${VM_NAME}" sudo cat /etc/rancher/k3s/k3s.yaml \
  | sed -e "s#server: https://127.0.0.1:6443#server: https://${VM_IP}:6443#" \
        -e "s/name: default/name: ${CONTEXT_NAME}/" \
        -e "s/cluster: default/cluster: ${CONTEXT_NAME}/" \
        -e "s/user: default/user: ${CONTEXT_NAME}/" \
        -e "s/current-context: default/current-context: ${CONTEXT_NAME}/" \
  > "${KUBECONFIG_PATH}"
chmod 600 "${KUBECONFIG_PATH}"

# 4. 검증 — k3s 기동 대기 (최대 120s)
log "노드 Ready 검증 중 (최대 120s 대기)"
elapsed=0
timeout=120
interval=5
until KUBECONFIG="${KUBECONFIG_PATH}" kubectl get nodes 2>/dev/null | grep -q " Ready "; do
  if [ "${elapsed}" -ge "${timeout}" ]; then
    log "타임아웃: ${timeout}s 내 노드가 Ready 상태가 되지 않음"
    KUBECONFIG="${KUBECONFIG_PATH}" kubectl get nodes || true
    exit 1
  fi
  log "노드 대기 중... (${elapsed}s/${timeout}s)"
  sleep "${interval}"
  elapsed=$((elapsed + interval))
done

log "검증 완료:"
KUBECONFIG="${KUBECONFIG_PATH}" kubectl get nodes

log "부트스트랩 완료. kubeconfig: ${KUBECONFIG_PATH}"
