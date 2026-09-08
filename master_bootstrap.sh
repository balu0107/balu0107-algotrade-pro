#!/bin/bash
set -e

echo "=== 1. Installing Helm ==="
curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

echo "=== 2. Installing NGINX Ingress Controller ==="
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update
helm install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx --create-namespace \
  --set controller.service.type=NodePort

echo "=== 3. Installing Argo CD via Helm ==="
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install argocd argo/argo-cd --namespace argocd

echo "=== 4. Deploying PostgreSQL Database ==="
kubectl create namespace default --dry-run=client -o yaml | kubectl apply -f -

cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: db
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: db
  template:
    metadata:
      labels:
        app: db
    spec:
      containers:
        - name: postgres
          image: postgres:18-alpine
          env:
            - name: POSTGRES_USER
              value: postgres
            - name: POSTGRES_PASSWORD
              value: superuser
            - name: POSTGRES_DB
              value: algotrade
          ports:
            - containerPort: 5432
              name: postgres
---
apiVersion: v1
kind: Service
metadata:
  name: db
  namespace: default
spec:
  ports:
    - port: 5432
      targetPort: 5432
  selector:
    app: db
EOF

echo "=== 5. Registering Argo CD Application ==="
cat <<EOF | kubectl apply -f -
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: algotrade-app
  namespace: argocd
spec:
  project: default
  source:
    repoURL: 'https://github.com/balu0107/balu0107-algotrade-pro'
    targetRevision: HEAD
    path: algotrade-chart
  destination:
    server: 'https://kubernetes.default.svc'
    namespace: default
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
EOF

echo "=== 6. Extracting NGINX NodePort and Generating Access URL ==="
# Wait briefly for the service to be allocated
sleep 10

# Extract the dynamic NodePort allocated to the NGINX ingress controller
NGINX_PORT=$(kubectl get svc -n ingress-nginx ingress-nginx-controller -o jsonpath='{.spec.ports[?(@.name=="http")].nodePort}')

# Fetch the public IP of the master node dynamically from AWS metadata service
MASTER_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 || hostname -I | awk '{print $1}')

ACCESS_URL="http://${MASTER_IP}:${NGINX_PORT}"

echo "============================================================"
echo " NGINX NodePort successfully detected: ${NGINX_PORT}"
echo " Master Node Public IP: ${MASTER_IP}"
echo " APPLICATION ACCESS URL: ${ACCESS_URL}"
echo "============================================================"

# Save the generated URL to a local log file for verification
sudo mkdir -p /var/log/algotrade
echo "${ACCESS_URL}" | sudo tee /var/log/algotrade/access-url.log

echo "=== Master Node Bootstrap Complete! ==="
echo "=== check url! ==="