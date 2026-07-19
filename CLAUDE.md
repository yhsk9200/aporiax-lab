# CLAUDE.md — aporiax-lab 세션 컨텍스트

이 레포는 ADR-0009(격리 ML/LLMOps 실험 클러스터)의 실험 플레인이다. 프로덕션 컨텍스트는 `~/projects/gitops-infra/CLAUDE.md`를 참조.

## 연결 계약 (요약 — 상세는 README.md·gitops-infra ADR-0009)

- **허용 3지점**: ① 전송로 tailnet ② 관측: OCI Grafana ← Mac Prometheus datasource(읽기 단방향) ③ 기록: Mac 워크로드 → OCI MLflow 클라이언트.
- **비연결**: OCI ArgoCD 원격 관리 금지 · 가용성 알림 금지 · 클러스터 간 스케줄링 금지 — 의존은 항상 Mac→OCI 단방향.

## 현재 상태 (2026-07-19)

Phase 1 부트스트랩 완료: VM `mlx-1`(OrbStack Ubuntu, arm64) + k3s `v1.32.13+k3s1`, kubeconfig `~/.kube/aporiax-lab.yaml`. Prometheus 배포 완료(2026-07-19, kube-prometheus-stack 83.6.0 — prod 패리티, grafana/AM 비활성, NodePort 30090). mlx-1 tailnet IP = `100.105.255.40`.

## 다음 작업

1. ~~VM에 tailscaled 설치·인증~~ → ✅ 완료 (2026-07-19, mlx-1 = 100.105.255.40)
2. ~~연결 계약 ② 이행~~ → ✅ 완료 (2026-07-19, gitops-infra PR #43): OCI Grafana에 aporiax-lab-prometheus datasource — ConfigMap 반영·sidecar 리로드 200 실측. 계약 ③(→OCI MLflow 기록)은 첫 실험 워크로드에서 실측 예정
3. ML/LLM 실험 스택 — **첫 슬라이스 계획 확정** (`docs/llm-slice-plan.md`, 2026-07-19): S1 WebUI→Ollama 직결(체감 UI) → S2 LiteLLM 게이트웨이 → S3 eval Job + 계약 ③ MLflow 기록 실측(선행: gitops-infra에 MLflow NodePort 30500 + allowed-hosts PR). Langfuse는 조건부 보류 — MLflow GenAI tracing으로 흡수. S1 ✅ 완료 (2026-07-19: 호스트 Ollama *:11434 재바인딩, ollama-host Endpoints=0.250.250.254, Open WebUI v0.10.2 NodePort 30080 — 파드→호스트 게이트·HTTP 200·브라우저 대화 눈검증까지 통과). 다음 착수점 = S2 (LiteLLM 게이트웨이)

## 명명 규칙

- VM 머신: `mlx-N`
- 네임스페이스: 실험별 자유 — 프로덕션의 `platform-*` 규칙은 이 레포에 적용하지 않는다(의도적).
