#!/bin/bash
# Load test script for Gemma4-e4b
# Sends concurrent inference requests to generate queue pressure,
# triggering HPA or KEDA autoscaling.

set -euo pipefail

NUM_REQUESTS=${1:-20}

ROUTE_URL=$(oc get route -l serving.kserve.io/inferenceservice=gemma-4-e4b -n gemma-model -o jsonpath='{.items[0].spec.host}')

if [ -z "${ROUTE_URL}" ]; then
  echo "ERROR: Could not find Route for gemma-4-e4b InferenceService."
  echo "Ensure the model is deployed: oc get inferenceservice gemma-4-e4b -n gemma-model"
  exit 1
fi

INFERENCE_URL="https://${ROUTE_URL}/v1/chat/completions"

echo "Target: ${INFERENCE_URL}"
echo "Sending ${NUM_REQUESTS} concurrent requests..."

for i in $(seq 1 "${NUM_REQUESTS}"); do
  curl -sk "${INFERENCE_URL}" \
    -H "Content-Type: application/json" \
    -d '{
      "model": "gemma-4-e4b",
      "messages": [{"role": "user", "content": "Write a 200-word essay about container orchestration."}],
      "max_tokens": 300
    }' > /dev/null 2>&1 &
done

echo "Waiting for requests to complete..."
wait
echo "Done. Check scaling with: oc get pods -n gemma-model -w"
