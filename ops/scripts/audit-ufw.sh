#!/usr/bin/env bash
# audit-ufw.sh — sanity-check UFW against the Sacred Brain baseline
# Usage: sudo ./audit-ufw.sh

set -euo pipefail

PASS=0
FAIL=0

ok()   { echo "✔ $1"; : $((PASS+=1)); return 0; }
bad()  { echo "✘ $1"; : $((FAIL+=1)); return 0; }
info() { echo "• $1"; return 0; }

require_root() {
  if [[ $EUID -ne 0 ]]; then
    echo "Run as root (sudo)." >&2
    exit 1
  fi
}

check_default_policies() {
  local status
  status=$(ufw status verbose)

  echo "$status" | grep -q "Default: deny (incoming), allow (outgoing), allow (routed)" \
    && ok "Default policies correct" \
    || bad "Default policies NOT correct"

  echo "$status" | grep -q "Logging: off" \
    && ok "UFW logging is off" \
    || bad "UFW logging is ON"
}

check_interface_rules() {
  local status
  status=$(ufw status)

  echo "$status" | grep -q "Anywhere on tailscale0" \
    && ok "tailscale0 allowed" \
    || bad "tailscale0 NOT allowed"

  echo "$status" | grep -q "Anywhere on docker0" \
    && ok "docker0 allowed" \
    || bad "docker0 NOT allowed"

  echo "$status" | grep -q "Anywhere on br-" \
    && ok "Docker bridge(s) allowed" \
    || bad "No Docker bridge rules found"
}

check_ports() {
  local status
  status=$(ufw status)

  echo "$status" | grep -q "80/tcp" \
    && ok "HTTP (80) allowed" \
    || bad "HTTP (80) not allowed"

  echo "$status" | grep -q "443/tcp" \
    && ok "HTTPS (443) allowed" \
    || bad "HTTPS (443) not allowed"

  echo "$status" | grep -q "8443/tcp" \
    && ok "Matrix federation (8443) allowed" \
    || bad "Matrix federation (8443) not allowed"

  echo "$status" | grep -q "22 on tailscale0" \
    && ok "SSH restricted to tailscale0" \
    || bad "SSH not restricted to tailscale0"

  echo "$status" | grep -q "4000 on tailscale0" \
    && ok "LiteLLM restricted to tailscale0" \
    || info "LiteLLM (4000) not restricted to tailscale0 (may be intentional)"
}

summary() {
  echo
  echo "Summary:"
  echo "  PASS: $PASS"
  echo "  FAIL: $FAIL"
  echo
  if (( FAIL == 0 )); then
    echo "UFW baseline looks GOOD." 
  else
    echo "UFW baseline has issues. Review above." 
    exit 2
  fi
}

main() {
  require_root
  echo "Running UFW baseline audit…"
  echo
  check_default_policies
  check_interface_rules
  check_ports
  summary
}

main "$@"

