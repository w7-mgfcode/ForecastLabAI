#!/usr/bin/env bash
# End-to-end smoke test for ForecastLabAI
# Usage: ./examples/e2e_smoke.sh

set -euo pipefail

API_URL="${API_URL:-http://localhost:8123}"

echo "=== ForecastLabAI E2E Smoke Test ==="
echo "API URL: $API_URL"
echo ""

# Test 1: Health check
echo "1. Testing /health endpoint..."
response=$(curl -s -w "\n%{http_code}" "$API_URL/health")
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')

if [ "$http_code" != "200" ]; then
    echo "   FAIL: Expected 200, got $http_code"
    exit 1
fi

status=$(echo "$body" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
if [ "$status" != "ok" ]; then
    echo "   FAIL: Expected status 'ok', got '$status'"
    exit 1
fi
echo "   PASS: Health check returned status=ok"

# Test 2: Request ID header
echo "2. Testing X-Request-ID header..."
request_id=$(curl -s -I "$API_URL/health" | grep -i "x-request-id" | tr -d '\r' | cut -d' ' -f2)

if [ -z "$request_id" ]; then
    echo "   FAIL: X-Request-ID header not found"
    exit 1
fi
echo "   PASS: X-Request-ID header present ($request_id)"

# Test 3: Custom request ID propagation
echo "3. Testing custom request ID propagation..."
custom_id="smoke-test-$(date +%s)"
returned_id=$(curl -s -I -H "X-Request-ID: $custom_id" "$API_URL/health" | grep -i "x-request-id" | tr -d '\r' | cut -d' ' -f2)

if [ "$returned_id" != "$custom_id" ]; then
    echo "   FAIL: Expected '$custom_id', got '$returned_id'"
    exit 1
fi
echo "   PASS: Custom request ID propagated correctly"

echo ""
echo "=== All smoke tests passed ==="
