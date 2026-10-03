#!/bin/sh
# regenerate the signing fixtures: a p-256 root and two leaves it issues
#
# the root's key is thrown away, so the files here are all the tests need.
# run from this directory with openssl 3.4 or later.
set -eu
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "$work/root.key"
openssl req -x509 -new -key "$work/root.key" -sha256 -subj "/O=mach-pdf/CN=mach-pdf test root" \
    -not_before 20260101000000Z -not_after 20460101000000Z \
    -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign" \
    -addext "subjectKeyIdentifier=hash" -out root.pem
openssl x509 -in root.pem -outform DER -out root.der

for who in signer witness; do
    openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "$who-key.pem"
    openssl req -new -key "$who-key.pem" -subj "/O=mach-pdf/CN=mach-pdf test $who" -out "$work/$who.csr"
    printf '%s\n' "basicConstraints=critical,CA:FALSE" "keyUsage=critical,digitalSignature,nonRepudiation" \
        "subjectKeyIdentifier=hash" "authorityKeyIdentifier=keyid" > "$work/$who.ext"
    openssl x509 -req -in "$work/$who.csr" -CA root.pem -CAkey "$work/root.key" -sha256 \
        -not_before 20260101000000Z -not_after 20460101000000Z -set_serial 0x$(openssl rand -hex 8) \
        -extfile "$work/$who.ext" -out "$who.pem"
done
