#!/usr/bin/env bash
# Setup script for L2-M6.2 — odo Developer CLI
# Creates the demo project, application files, and initializes odo
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LESSON_DIR="$(dirname "$SCRIPT_DIR")"
WORK_DIR="/tmp/odo-lesson"

echo "=== L2-M6.2: odo Developer CLI — Setup ==="

# Check prerequisites
echo ""
echo "--- Checking prerequisites ---"

if ! command -v oc &> /dev/null; then
  echo "ERROR: 'oc' CLI not found. Install it first."
  exit 1
fi

if ! command -v odo &> /dev/null; then
  echo "ERROR: 'odo' CLI not found."
  echo "Install it with:"
  echo "  curl -L https://developers.redhat.com/content-gateway/rest/mirror/pub/openshift-v4/clients/odo/v3.16.1/odo-darwin-arm64 -o odo"
  echo "  chmod +x odo && sudo mv odo /usr/local/bin/"
  exit 1
fi

if ! oc whoami &> /dev/null; then
  echo "ERROR: Not logged into OpenShift. Run 'oc login' first."
  exit 1
fi

echo "  oc version: $(oc version --client --short 2>/dev/null || oc version --client)"
echo "  odo version: $(odo version --client 2>/dev/null || odo version)"
echo "  Logged in as: $(oc whoami)"
echo "  Server: $(oc whoami --show-server)"

# Create project
echo ""
echo "--- Creating OpenShift project ---"
oc new-project odo-demo 2>/dev/null || oc project odo-demo
echo "  Project: odo-demo"

# Create working directory
echo ""
echo "--- Creating application files ---"
mkdir -p "$WORK_DIR"

cat > "$WORK_DIR/app.js" << 'APPEOF'
const http = require("http");

const PORT = 3000;

const server = http.createServer((req, res) => {
  res.writeHead(200, { "Content-Type": "application/json" });
  res.end(JSON.stringify({
    message: "Hello from odo!",
    timestamp: new Date().toISOString(),
    path: req.url,
  }));
});

server.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
APPEOF

cat > "$WORK_DIR/package.json" << 'PKGEOF'
{
  "name": "odo-demo",
  "version": "1.0.0",
  "description": "Demo app for odo lesson",
  "main": "app.js",
  "scripts": {
    "start": "node app.js",
    "dev": "node --watch app.js"
  }
}
PKGEOF

cat > "$WORK_DIR/Dockerfile" << 'DEOF'
FROM registry.access.redhat.com/ubi9/nodejs-20-minimal:latest
COPY package.json ./
RUN npm install --production
COPY app.js ./
EXPOSE 3000
CMD ["node", "app.js"]
DEOF

# Copy deploy manifests
mkdir -p "$WORK_DIR/manifests"
cp "$LESSON_DIR/manifests/deployment.yaml" "$WORK_DIR/manifests/"

echo "  Created: $WORK_DIR/app.js"
echo "  Created: $WORK_DIR/package.json"
echo "  Created: $WORK_DIR/Dockerfile"
echo "  Created: $WORK_DIR/manifests/deployment.yaml"

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  cd $WORK_DIR"
echo "  odo init --name odo-demo --devfile nodejs --devfile-registry DefaultDevfileRegistry"
echo "  odo dev"
echo ""
echo "See the README.md for the full walkthrough."
