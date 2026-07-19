#!/usr/bin/env bash
# Phase 2 부트스트랩: 경량 Prometheus (kube-prometheus-stack, ADR-0009 실험 플레인)
# grafana/alertmanager 비활성 — 관측은 OCI Grafana가 datasource로 봄 (연결 계약 ②).
# idempotent — 재실행해도 안전.
set -euo pipefail

export KUBECONFIG="${HOME}/.kube/aporiax-lab.yaml"
NAMESPACE="monitoring"
RELEASE="monitoring"
CHART_VERSION="83.6.0"
VALUES_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/helm-values/monitoring/kube-prometheus-stack-values.yaml"
STS_NAME="prometheus-${RELEASE}-kube-prometheus-prometheus"

log() {
  echo "[bootstrap] $*"
}

# 1. helm repo 등록 (이미 있으면 무시)
log "prometheus-community repo 확인 중"
if helm repo list | grep -q "^prometheus-community"; then
  log "prometheus-community repo 이미 등록됨 — add 스킵"
else
  log "prometheus-community repo 추가 중"
  helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
fi
helm repo update prometheus-community

# 2. 설치/업그레이드
log "kube-prometheus-stack ${CHART_VERSION} 설치/업그레이드 중 (namespace: ${NAMESPACE})"
helm upgrade --install "${RELEASE}" prometheus-community/kube-prometheus-stack \
  --version "${CHART_VERSION}" \
  -n "${NAMESPACE}" --create-namespace \
  -f "${VALUES_FILE}"

# 3. 롤아웃 완료 대기
log "Prometheus StatefulSet 롤아웃 대기 중: ${STS_NAME}"
kubectl -n "${NAMESPACE}" rollout status "statefulset/${STS_NAME}" --timeout=300s

# 4. 검증 출력
log "검증 완료:"
kubectl get pods -n "${NAMESPACE}"

log "부트스트랩 완료. NodePort 30090 (tailnet 경유 전용)."
