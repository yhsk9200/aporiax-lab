# 실행계획 5 — 첫 슬라이스: UI-보이는 LLM 스택 (계획, 2026-07-19)

목표: "MLflow 예제 수준" 탈출의 1단계. 커스텀 UI를 만들기 전에, **기성 UI가 딸린
스택을 수직 슬라이스로** 세워 (a) 손쉽게 쓰는 LLM 화면을 즉시 체감하고
(b) LLMOps의 실체(게이트웨이·추적·eval)를 굴리고 (c) ADR-0009 연결 계약
③(Mac 워크로드 → OCI MLflow 기록)을 실측한다.

**환경 실측 (2026-07-19)**: Ollama 0.32.1 설치됨 + 모델 보유(gemma4:12b 7.6GB
·26b·31b, gemma2:27b) — 모델 준비 불필요. VM에서 `host.orb.internal` 해석
확인(IPv6 우선 응답 — 파드는 IPv4 단일 스택이라 **S1에서 IPv4 주소 실측 필요**).

## 아키텍처 (배치 원칙: 추론=호스트 Metal, 나머지=k8s CPU)

```
[Mac 호스트]  Ollama (Metal GPU, OLLAMA_HOST=0.0.0.0 재바인딩 필요)
     ↑ VM→호스트 IPv4 (Service+Endpoints "ollama-host"로 클러스터 DNS화)
[mlx-1 클러스터]  Open WebUI (S1, NodePort 30080) → LiteLLM 게이트웨이 (S2)
     └─ eval Job (S3) ── tailnet ──→ [OCI] MLflow (계약 ③: run·trace·아티팩트 기록)
```

**Langfuse 도입 보류 (결정)**: v3 스택은 postgres+clickhouse+redis+S3 4종 상시
— 실험 플레인에도 과하다. LLM 추적·eval 기록은 **OCI MLflow 3.x의 GenAI
tracing/evaluate로 흡수** — 신규 컴포넌트 0, 기존 자산 소비, 계약 ③ 실증 겸용.
재검토 조건: 트레이스 탐색 UI가 실사용에서 병목으로 확인되면.

## S1 — 체감 UI (WebUI → Ollama 직결)

1. (수동/스크립트) Ollama를 `OLLAMA_HOST=0.0.0.0`으로 재기동 — 노출 표면은 홈
   NAT 뒤 LAN + tailnet뿐(무인증이므로 공인 노출 절대 금지, 실험 플레인 수용
   리스크로 기록. 신경 쓰이면 tailscale ACL로 11434 제한)
2. VM→호스트 IPv4 실측: `orb -m mlx-1 getent ahostsv4 host.orb.internal`
   → 파드에서 `curl <IPv4>:11434/api/tags` 통과 확인
3. `manifests/llm/ollama-host-endpoint.yaml`: Service(clusterIP 없는 headless
   아님 — ClusterIP) + 수동 Endpoints로 호스트 IPv4:11434를 `ollama-host`
   DNS로 고정 (IP 하드코딩을 한 곳에 격리)
4. `manifests/llm/open-webui.yaml`: Deployment(+PVC local-path 2Gi) + NodePort
   30080. env `OLLAMA_BASE_URL=http://ollama-host:11434`
5. 검증 게이트: 브라우저 `http://192.168.139.61:30080` → 가입(로컬 계정) →
   gemma4:12b 채팅 응답. (tailnet IP로도 접근 가능 — 폰에서 쓸 수 있음)

## S2 — 게이트웨이 (LiteLLM)

1. `manifests/llm/litellm.yaml`: Deployment + ConfigMap(model_list:
   ollama/gemma4:12b 등 보유 모델, api_base=http://ollama-host:11434) +
   Service 4000. 이미지 arm64 manifest 선검증 필수(ADR-0006 교훈 —
   `docker buildx imagetools inspect`)
2. Open WebUI에 OpenAI-호환 커넥터로 LiteLLM 등록 → 경유 대화 확인
3. 검증 게이트: 파드에서 `/v1/chat/completions` 200 + WebUI 경유 응답.
   게이트웨이의 존재 이유(모델 라우팅·예산·키 관리)는 이후 모델·백엔드가
   늘 때 발현 — S2에서는 배선까지만

## S3 — eval 루프 + 계약 ③ 실측 (MLflow 기록)

**선행 (gitops-infra 쪽 작은 PR 1건)**: OCI MLflow는 ClusterIP 전용이라 Mac
클러스터에서 접근 불가 → Service를 NodePort 30500으로 (tailnet 경유 전용 —
Security List가 공인 차단하므로 노출 표면 불변, ADR-0008 "터널/tailnet 전용"
범위 내). **함정 선반영**: MLflow allowed-hosts에 `100.69.52.25:30500` 추가
필요 (Host 헤더 검증 — 활성화 때 실측한 그 함정).

1. `eval/` 디렉토리: 프롬프트셋(YAML, 소규모 — 예: 한국어 요약·코드 생성
   10문항) + 러너 스크립트(게이트웨이 호출 → 응답·지연·토큰 기록 →
   `MLFLOW_TRACKING_URI=http://100.69.52.25:30500`로 run/metrics/아티팩트 업로드)
2. k8s Job으로 실행 (CronJob 승격은 반복 실수요 등장 시)
3. 검증 게이트: OCI MLflow UI(port-forward)에서 eval experiment의 run·비교
   테이블 확인 = **계약 ③ 실측 완료**

## 실행 분담

- 계획·검증 게이트 = Fable / 매니페스트·스크립트·배포 = Sonnet (전역 라우팅 룰)
- 수동(위임 불가): Ollama 재바인딩 승인, WebUI 첫 가입, gitops-infra PR 머지

## 비목표 (이 슬라이스에서 안 하는 것)

- 커스텀 통합 UI — 기성 UI로 루프를 돌리며 실마찰이 보인 뒤 별도 테넌트로
  (ADR-0001 기각 사유 재검토와 함께)
- RAG/벡터 DB — eval 루프가 자리 잡은 뒤 다음 슬라이스
- 멀티노드 스케줄링 — 별도 실험 트랙
