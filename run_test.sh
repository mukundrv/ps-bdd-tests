#!/bin/bash

set -e  # Exit on first error
set -o pipefail

# Step 1: Set up Python virtual environment
echo "Setting up Python environment..."
cd app
k

# Step 2: Apply Kubernetes YAMLs in order
PVC_NAME="persistent-pvc"
PVC_NAMESPACE="ps" 

echo "Applying PersistentVolume..."
kubectl apply -f "examples/persistent-pv.yaml" -n "$PVC_NAMESPACE" 

echo "Applying PersistentVolumeClaim..."
kubectl apply -f "examples/persistent-pvc.yaml" -n "$PVC_NAMESPACE"

# Step 2.5: Wait until PVC is bound
echo "Checking if PVC is bound..."

for i in {1..30}; do
  status=$(kubectl get pvc "$PVC_NAME" -n "$PVC_NAMESPACE" -o jsonpath='{.status.phase}')
  echo "PVC status: $status"
  if [ "$status" == "Bound" ]; then
    echo "PVC is bound."
    break
  fi
  echo "Waiting for PVC to be bound..."
  sleep 5
done

if [ "$status" != "Bound" ]; then
  echo "PVC did not bind within timeout. Exiting."
  exit 1
fi

# Step 3: Apply deployment.yaml
echo "Applying Deployment..."
kubectl apply -f "examples/deployment.yaml"

# Step 4: Wait for deployment to be ready
echo "Waiting for deployment to be ready..."
kubectl rollout status deployment/ps-test -n ps

# Step 3: Run pytest
echo "Running tests..."
export PYTHONPATH=.
pytest -v --log-cli-level=INFO src/tests/ --exitfirst