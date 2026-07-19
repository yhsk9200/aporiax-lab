# aporiax-lab — 격리 ML/LLMOps 실험 클러스터 (Mac)

## 역할

프로덕션 플랫폼([gitops-infra](https://github.com/yhsk9200/gitops-infra), OCI k3s)과 분리된 실험 플레인이다. 배경·근거는 gitops-infra의 [ADR-0009](https://github.com/yhsk9200/gitops-infra/blob/main/docs/adr/0009-isolated-ml-experiment-cluster.md)를 참조.

## 연결 계약 (3지점만 허용, 나머지 기본 거부)

1. **전송로**: tailnet.
2. **관측**: OCI Grafana ← Mac Prometheus datasource (읽기 단방향).
3. **기록**: Mac 워크로드 → OCI MLflow 클라이언트.

**비연결 명시**: OCI ArgoCD 원격 관리 금지 · 가용성 알림 금지 · 클러스터 간 스케줄링 금지 — 의존은 항상 Mac→OCI 단방향이다.

## 토폴로지

- OrbStack Ubuntu VM(arm64) server 1대 + k3s v1.32.13+k3s1 (프로덕션 버전 패리티 핀).
- 멀티노드는 스케줄링 실험이 필요해질 때 agent 증설.
- GPU 워크로드는 k8s 밖 macOS 네이티브(Ollama/MLX) 하이브리드 — VM에 Metal 패스스루 부재.

## GitOps 도구 결정

시작은 plain manifests + `kubectl apply -k`다. ArgoCD 재설치는 prod에서 이미 증명한 것의 반복이고, Flux는 이 실험(ML 스택) 목적 밖의 표면이라 도입하지 않는다. 재구축 반복·드리프트 관리가 실수요로 등장하면 도입을 재검토한다.

prod와의 규율 차등도 의도적이다: main 직접 푸시를 허용하고(실험 플레인 — 파괴·재구축이 전제), 브랜치 보호는 두지 않는다.

## 부트스트랩

```bash
bash bootstrap/01-vm-k3s.sh
```

VM(mlx-1) 생성 → k3s 설치 → kubeconfig를 `~/.kube/aporiax-lab.yaml`로 추출 → 노드 Ready 검증까지 idempotent하게 수행한다.
