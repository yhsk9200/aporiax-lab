#!/usr/bin/env python3
"""S3 eval 러너 — docs/llm-slice-plan.md S3.

LiteLLM 게이트웨이(OpenAI 호환 /v1/chat/completions)로 prompts.yaml의 문항을
순서대로 호출해 응답·지연·토큰을 측정하고, OCI MLflow에 run/metrics/artifact로
기록한다. proxied artifacts(MLflow 서버 --serve-artifacts)라 S3 자격증명 없이
MLFLOW_TRACKING_URI만으로 아티팩트 업로드까지 된다.

환경변수:
  GATEWAY_URL          기본 http://litellm.llm.svc.cluster.local:4000
  MLFLOW_TRACKING_URI  (필수 — 클러스터에서 env로 주입됨)
  EVAL_MODEL           기본 gemma4-12b
  PROMPTS_PATH         기본 /eval/prompts.yaml

개별 문항의 게이트웨이 호출 실패는 그 문항만 pass=False로 기록하고 계속
진행한다(전체 Job을 죽이지 않음). MLflow 연결/기록 실패는 잡의 목적 자체가
무의미해지므로 명확한 에러 메시지와 함께 exit 1.
"""
import json
import os
import statistics
import sys
import tempfile
import time

import requests
import yaml

import mlflow


def load_prompts(path):
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    items = data["prompts"]
    if not items:
        raise ValueError(f"프롬프트가 비어 있음: {path}")
    return items


def call_gateway(gateway_url, model, prompt, timeout=60):
    """게이트웨이에 단일 문항을 호출한다.

    반환: dict(latency_s, completion_tokens, prompt_tokens, response_text, error)
    실패해도 예외를 올리지 않고 error 필드에 사유를 담아 반환한다 — 호출부가
    이 문항만 pass=False로 처리하고 나머지 문항을 계속 진행할 수 있게 하기 위함.
    """
    url = f"{gateway_url}/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    start = time.monotonic()
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        latency_s = time.monotonic() - start
        resp.raise_for_status()
        body = resp.json()
        response_text = body["choices"][0]["message"]["content"]
        usage = body.get("usage", {}) or {}
        return {
            "latency_s": latency_s,
            "completion_tokens": usage.get("completion_tokens", 0),
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "response_text": response_text,
            "error": None,
        }
    except Exception as exc:  # 게이트웨이 호출 실패 — 문항 단위로 흡수
        latency_s = time.monotonic() - start
        return {
            "latency_s": latency_s,
            "completion_tokens": 0,
            "prompt_tokens": 0,
            "response_text": "",
            "error": str(exc),
        }


def run_eval(prompts, gateway_url, model):
    results = []
    for item in prompts:
        call = call_gateway(gateway_url, model, item["prompt"])
        expect = item.get("expect_substring", "")
        passed = bool(expect) and expect in call["response_text"] and call["error"] is None
        results.append(
            {
                "id": item["id"],
                "category": item["category"],
                "prompt": item["prompt"],
                "expect_substring": expect,
                "pass": passed,
                "latency_s": call["latency_s"],
                "completion_tokens": call["completion_tokens"],
                "prompt_tokens": call["prompt_tokens"],
                "response_text": call["response_text"],
                "error": call["error"],
            }
        )
    return results


def percentile(values, pct):
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    k = (len(ordered) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(ordered) - 1)
    if f == c:
        return ordered[f]
    return ordered[f] + (ordered[c] - ordered[f]) * (k - f)


def compute_metrics(results):
    latencies = [r["latency_s"] for r in results]
    completion_tokens = [r["completion_tokens"] for r in results]
    pass_count = sum(1 for r in results if r["pass"])
    return {
        "pass_rate": pass_count / len(results) if results else 0.0,
        "avg_latency_s": statistics.fmean(latencies) if latencies else 0.0,
        "p95_latency_s": percentile(latencies, 95),
        "total_completion_tokens": sum(completion_tokens),
        "avg_completion_tokens": statistics.fmean(completion_tokens) if completion_tokens else 0.0,
    }


def main():
    gateway_url = os.environ.get("GATEWAY_URL", "http://litellm.llm.svc.cluster.local:4000")
    model = os.environ.get("EVAL_MODEL", "gemma4-12b")
    prompts_path = os.environ.get("PROMPTS_PATH", "/eval/prompts.yaml")
    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI")

    if not tracking_uri:
        print("ERROR: MLFLOW_TRACKING_URI가 설정되어 있지 않음 — 기록 대상 없이 실행 불가", file=sys.stderr)
        sys.exit(1)

    mlflow.set_tracking_uri(tracking_uri)

    # MLflow 연결 확인을 먼저 해서, 이후 게이트웨이 호출에 시간을 쓰고 나서야
    # 기록 불가를 발견하는 낭비를 막는다.
    try:
        mlflow.set_experiment("llm-eval")
    except Exception as exc:
        print(f"ERROR: MLflow 연결 실패 (tracking_uri={tracking_uri}): {exc}", file=sys.stderr)
        sys.exit(1)

    prompts = load_prompts(prompts_path)
    results = run_eval(prompts, gateway_url, model)
    metrics = compute_metrics(results)

    try:
        with mlflow.start_run(run_name=f"{model}-{len(prompts)}q"):
            mlflow.log_params(
                {
                    "model": model,
                    "gateway_url": gateway_url,
                    "prompt_count": len(prompts),
                }
            )
            mlflow.log_metrics(
                {
                    "pass_rate": metrics["pass_rate"],
                    "avg_latency_s": metrics["avg_latency_s"],
                    "p95_latency_s": metrics["p95_latency_s"],
                    "total_completion_tokens": metrics["total_completion_tokens"],
                    "avg_completion_tokens": metrics["avg_completion_tokens"],
                }
            )
            for i, r in enumerate(results):
                mlflow.log_metric("latency_s", r["latency_s"], step=i)

            with tempfile.TemporaryDirectory() as tmpdir:
                results_path = os.path.join(tmpdir, "results.json")
                with open(results_path, "w", encoding="utf-8") as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)
                mlflow.log_artifact(results_path)
    except Exception as exc:
        print(f"ERROR: MLflow run 기록 실패 (tracking_uri={tracking_uri}): {exc}", file=sys.stderr)
        sys.exit(1)

    print(
        f"pass_rate={metrics['pass_rate']:.2f} "
        f"avg_latency_s={metrics['avg_latency_s']:.2f} "
        f"model={model} prompt_count={len(prompts)}"
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
