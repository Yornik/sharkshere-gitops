#!/usr/bin/env bash
set -euo pipefail

config_file="${1:-manifests/traefik-config/configmap-security-txt.yaml}"

if [[ ! -f "$config_file" ]]; then
  echo "security.txt config file not found: $config_file" >&2
  exit 1
fi

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

extract_block() {
  local block_name="$1"

  awk -v block_name="$block_name" '
    $0 == "  " block_name ": |" { in_block = 1; next }
    in_block && $0 ~ /^  [^ ]/ { exit }
    in_block {
      if ($0 == "") {
        print ""
        next
      }
      if (substr($0, 1, 4) != "    ") {
        print "invalid indentation in block " block_name > "/dev/stderr"
        exit 2
      }
      print substr($0, 5)
    }
  ' "$config_file"
}

security_txt="$workdir/security.txt"
pgp_key="$workdir/pgp-key.txt"
plain_txt="$workdir/security-plain.txt"
gnupg_home="$workdir/gnupg"

extract_block "security.txt" > "$security_txt"
extract_block "pgp-key.txt" > "$pgp_key"

[[ -s "$security_txt" ]] || { echo "security.txt block is empty" >&2; exit 1; }
[[ -s "$pgp_key" ]] || { echo "pgp-key.txt block is empty" >&2; exit 1; }

grep -q '^-----BEGIN PGP SIGNED MESSAGE-----$' "$security_txt" || {
  echo "security.txt is not a clearsigned message" >&2
  exit 1
}

grep -q '^-----BEGIN PGP PUBLIC KEY BLOCK-----$' "$pgp_key" || {
  echo "pgp-key.txt does not contain an armored public key" >&2
  exit 1
}

mkdir -p "$gnupg_home"
chmod 700 "$gnupg_home"

GNUPGHOME="$gnupg_home" gpg --batch --import "$pgp_key" >/dev/null 2>&1
GNUPGHOME="$gnupg_home" gpg --batch --verify "$security_txt" >/dev/null 2>&1
GNUPGHOME="$gnupg_home" gpg --batch --decrypt "$security_txt" > "$plain_txt"

grep -q '^Contact: ' "$plain_txt" || { echo "missing Contact field" >&2; exit 1; }
grep -q '^Expires: ' "$plain_txt" || { echo "missing Expires field" >&2; exit 1; }
grep -q '^Encryption: https://.*' "$plain_txt" || { echo "missing valid Encryption field" >&2; exit 1; }
grep -q '^Canonical: https://.*/\.well-known/security\.txt$' "$plain_txt" || {
  echo "missing Canonical field" >&2
  exit 1
}

if grep '^Canonical: ' "$plain_txt" | grep -qvE '^Canonical: https://.*/\.well-known/security\.txt$'; then
  echo "one or more Canonical fields are not valid https security.txt URLs" >&2
  exit 1
fi

echo "security.txt signature and required fields are valid"
