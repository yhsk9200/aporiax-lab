# eval/ — LLM 게이트웨이 eval 루프 (S3)

목적: ADR-0009 연결 계약 ③(Mac 워크로드 → OCI MLflow 클라이언트 기록)의
실증. LiteLLM 게이트웨이(S2)를 경유해 소규모 프롬프트셋을 돌리고, 응답
지연·토큰·pass_rate를 OCI MLflow에 run으로 기록한다. 상세 계획은
`docs/llm-slice-plan.md`의 S3 절 참조.

이 디렉토리(`eval/prompts.yaml`, `eval/run_eval.py`)는 소스 원본이다. 실제
실행은 `manifests/llm/eval-job.yaml`의 ConfigMap에 임베드된 사본이 클러스터
안에서 도는 것 — **두 파일 수정 시 반드시 양쪽에 반영할 것** (드리프트 방지,
`manifests/llm/eval-job.yaml` 상단 주석 참조).

## 실행법

```bash
kubectl delete job llm-eval -n llm --ignore-not-found
kubectl apply -f manifests/llm/eval-job.yaml
kubectl logs -f job/llm-eval -n llm
```

Job은 `batch/v1 Job`이라 스펙 대부분이 immutable — 재실행 시 반드시 삭제
후 재적용(위 커맨드 순서 그대로).

## 결과 확인법

OCI MLflow UI(SSH 터널 또는 tailnet 경유)에서 `llm-eval` experiment를 열어
run을 확인한다. run 이름은 `<EVAL_MODEL>-<문항수>q` 형식(예:
`gemma4-12b-10q`). 확인 포인트:

- 파라미터: `model`, `gateway_url`, `prompt_count`
- 지표: `pass_rate`, `avg_latency_s`, `p95_latency_s`,
  `total_completion_tokens`, `avg_completion_tokens`, 문항별 시계열
  `latency_s`(step=문항 인덱스)
- 아티팩트: `results.json` — 문항별 id·category·pass·latency·tokens·응답
  전문

## 모델 비교하는 법

`manifests/llm/eval-job.yaml`의 Job env에서 `EVAL_MODEL` 값을
`gemma4-26b`·`gemma4-31b`·`gemma2-27b` 등 게이트웨이에 등록된 다른
model_name으로 바꿔 재실행하면, 같은 `llm-eval` experiment 안에 run이
누적되어 MLflow UI의 run 비교 테이블(체크박스로 다중 선택 → Compare)에서
모델별 pass_rate·지연·토큰을 나란히 볼 수 있다.
