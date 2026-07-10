#!/usr/bin/env bash
# Render every external Helm chart with the values it will actually receive.
#
# CI's "helm template apps/" only renders the Application envelopes — it
# never checks the inline values blocks against the upstream charts they
# configure, so a chart release that rejects our values (e.g. traefik 41.x
# refusing the top-level `logs` key) sails through CI and only fails later
# as an ArgoCD ComparisonError. This script closes that gap: it renders the
# app-of-apps chart, then for each chart-sourced Application renders the
# upstream chart at the pinned version with the exact values from the
# Application spec.
set -euo pipefail

KUBE_VERSION="${KUBE_VERSION:-1.36.2}"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

helm template sharkshere-apps apps/ --namespace argocd > "$WORKDIR/rendered.yaml"

# One JSON object per chart-sourced Application, with the values verbatim
# as ArgoCD would pass them to the chart.
yq ea -o=json '[select(.kind == "Application" and .spec.source.chart != null) | {
  "name": .metadata.name,
  "repo": .spec.source.repoURL,
  "chart": .spec.source.chart,
  "version": .spec.source.targetRevision,
  "namespace": .spec.destination.namespace,
  "values": (.spec.source.helm.values // "")
}]' "$WORKDIR/rendered.yaml" > "$WORKDIR/apps.json"

count=$(jq length "$WORKDIR/apps.json")
echo "Validating $count chart applications against kube ${KUBE_VERSION}"

fail=0
for i in $(seq 0 $((count - 1))); do
  app=$(jq -r ".[$i]" "$WORKDIR/apps.json")
  name=$(jq -r '.name' <<<"$app")
  repo=$(jq -r '.repo' <<<"$app")
  chart=$(jq -r '.chart' <<<"$app")
  version=$(jq -r '.version' <<<"$app")
  namespace=$(jq -r '.namespace' <<<"$app")
  jq -r '.values' <<<"$app" > "$WORKDIR/values.yaml"

  echo "==> ${name}: ${chart}@${version} (${repo})"
  if ! helm template "$name" "$chart" \
      --repo "$repo" \
      --version "$version" \
      --namespace "$namespace" \
      --kube-version "$KUBE_VERSION" \
      --include-crds \
      -f "$WORKDIR/values.yaml" > "$WORKDIR/${name}.rendered.yaml"; then
    echo "FAIL: ${name} (${chart}@${version}) does not render with its values"
    fail=1
  fi
done

if [ "$fail" -ne 0 ]; then
  echo
  echo "One or more charts failed to render — this would be an ArgoCD"
  echo "ComparisonError after merge, not a working deployment."
  exit 1
fi
echo "All ${count} charts render cleanly with their values."
