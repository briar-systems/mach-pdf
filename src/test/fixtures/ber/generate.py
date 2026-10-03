#!/usr/bin/env python3
# writes signed.pdf and root.der: the two-signature file of ../okular, but with
# real signatures. each signature is the indefinite-length ber openssl cms
# -stream emits, a p-384 key signing with sha-256, under a generated root and
# intermediate. the leaf carries emailProtection and the adobe and microsoft
# document signing usages, as briar's certificates do. the keys are generated
# on every run and discarded, so the output differs each time.
# run: python3 generate.py (writes signed.pdf and root.der beside it)

import os
import subprocess
import sys
import tempfile

here = os.path.dirname(os.path.abspath(__file__))
work = tempfile.mkdtemp()

out = bytearray()
xref = {}
GAP = 2048


def run(*args, data=None):
    return subprocess.run(args, check=True, input=data, capture_output=True, cwd=work).stdout


def key(name):
    run("openssl", "genpkey", "-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-384", "-out", name + ".key")


def certify(name, subject, issuer, ext):
    key(name)
    open(os.path.join(work, name + ".ext"), "w").write(ext)
    run("openssl", "req", "-new", "-key", name + ".key", "-subj", "/CN=" + subject, "-out", name + ".csr")
    sign = ["-signkey", name + ".key"] if issuer is None else ["-CA", issuer + ".pem", "-CAkey", issuer + ".key", "-CAcreateserial"]
    run("openssl", "x509", "-req", "-in", name + ".csr", "-sha384", "-not_before", "20200101000000Z",
        "-not_after", "20700101000000Z", "-extfile", name + ".ext", "-out", name + ".pem", *sign)


certify("root", "Test Root", None, "basicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,cRLSign\n")
certify("inter", "Test Intermediate", "root",
        "basicConstraints=critical,CA:TRUE,pathlen:0\nkeyUsage=critical,keyCertSign,cRLSign\n")
certify("leaf", "Test Signer", "inter",
        "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,nonRepudiation\n"
        "extendedKeyUsage=emailProtection,1.2.840.113583.1.1.5,1.3.6.1.4.1.311.10.3.12\n")


def skip(der, at):
    # the end of the ber element at at
    at += 1
    first = der[at]
    at += 1
    if first == 0x80:
        while der[at:at + 2] != b"\0\0":
            at = skip(der, at)
        return at + 2
    if first < 0x80:
        return at + first
    count = first & 0x7f
    return at + count + int.from_bytes(der[at:at + count], "big")


def cms(data):
    # -stream signs opaquely, so the content is cut out of the encapsulated
    # content info, which leaves the detached signature the pdf holds
    der = run("openssl", "cms", "-sign", "-binary", "-stream", "-outform", "DER", "-md", "sha256",
              "-signer", "leaf.pem", "-inkey", "leaf.key", "-certfile", "inter.pem", data=data)
    oid = bytes.fromhex("06092a864886f70d010701")
    at = der.index(oid) + len(oid)
    if der[at:at + 2] != b"\xa0\x80":
        sys.exit("the signature has no indefinite content")
    der = der[:at] + der[skip(der, at):]
    if len(der) > GAP:
        sys.exit("signature of %d bytes does not fit the %d reserved" % (len(der), GAP))
    return der + bytes(GAP - len(der))


def put(s):
    out.extend(s.encode("latin1"))


def obj(n, gen, body):
    xref[n] = (len(out), gen)
    put("%d %d obj\n%s\nendobj\n" % (n, gen, body))


def stream(n, gen, dict_, data):
    obj(n, gen, "<< %s /Length %d >>\nstream\n%s\nendstream" % (dict_, len(data), data))


def section(prev):
    at = len(out)
    put("xref\n0 1\n0000000000 65535 f \n")
    nums = sorted(xref)
    i = 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        put("%d %d\n" % (nums[i], j - i + 1))
        for n in nums[i:j + 1]:
            off, gen = xref[n]
            put("%010d %05d n \n" % (off, gen))
        i = j + 1
    trailer = "<< /Size 14 /Root 1 0 R"
    if prev is not None:
        trailer += " /Prev %d" % prev
    put("trailer\n%s >>\nstartxref\n%d\n%%%%EOF\n" % (trailer, at))
    return at


def signature(n, name):
    # the byte range is patched once the revision's length is known
    start = len(out)
    body = ("<< /Type /Sig /Filter /Adobe.PPKLite /SubFilter /adbe.pkcs7.detached /Name (Signer) "
            "/M (D:20261003191410-04'00') /Contents <%s> /ByteRange [0 %010d %010d %010d] >>"
            % ("0" * (GAP * 2), 0, 0, 0))
    obj(n, 0, body)
    return start


def patch(start, end):
    at = out.index(b"/Contents <", start) + len(b"/Contents ")
    gap_end = at + GAP * 2 + 2
    text = ("/ByteRange [0 %010d %010d %010d]" % (at, gap_end, end - gap_end)).encode()
    pos = out.index(b"/ByteRange [", start)
    out[pos:pos + len(text)] = text


put("%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
obj(1, 0, "<< /Type /Catalog /Pages 2 0 R /AcroForm 5 0 R >>")
obj(2, 0, "<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
obj(3, 0, "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Annots [8 0 R 11 0 R] >>")
stream(4, 0, "", "BT /F1 12 Tf 72 700 Td (Agreement) Tj ET")
obj(5, 0, "<< /Fields [6 0 R 9 0 R] /DA (/F1 11 Tf 0 g) /SigFlags 1 >>")
for field, widget, empty, name, y in ((6, 8, 7, "first", 600), (9, 11, 10, "second", 500)):
    obj(field, 0, "<< /FT /Sig /T (%s) /Kids [%d 0 R] >>" % (name, widget))
    stream(empty, 0, "/Type /XObject /Subtype /Form /BBox [0 0 200 40]", "")
    obj(widget, 0, "<< /Type /Annot /Subtype /Widget /Rect [72 %d 272 %d] /P 3 0 R /F 4 /Parent %d 0 R "
        "/AP << /N %d 0 R >> >>" % (y, y + 40, field, empty))
first = section(None)

# okular reuses the empty stream's number at a new generation
def sign(field, widget, empty, sig, name, y, prev, flags):
    stream(empty, 1, "/Type /XObject /Subtype /Form /BBox [0 0 200 40]", "0.9 g 0 0 200 40 re f")
    obj(field, 0, "<< /FT /Sig /T (%s) /Kids [%d 0 R] /V %d 0 R >>" % (name, widget, sig))
    obj(widget, 0, "<< /Type /Annot /Subtype /Widget /Rect [72 %d 272 %d] /P 3 0 R /F 4 /Parent %d 0 R "
        "/Border [0 0 1.5] /M (D:20261003191410-04'00') /AP << /N %d 1 R >> /AS /N >>" % (y, y + 40, field, empty))
    if flags:
        obj(5, 0, "<< /Fields [6 0 R 9 0 R] /DA (/F1 11 Tf 0 g) /SigFlags 3 >>")
    start = signature(sig, name)
    at = section(prev)
    patch(start, len(out))
    gap = out.index(b"/Contents <", start) + len(b"/Contents <")
    signed = bytes(out[:gap - 1]) + bytes(out[gap + GAP * 2 + 1:])
    out[gap:gap + GAP * 2] = cms(signed).hex().encode()
    return at

# each update's cross-reference section lists only what it writes
xref.clear()
second = sign(6, 8, 7, 12, "first", 600, first, True)
xref.clear()
third = sign(9, 11, 10, 13, "second", 500, second, False)
open(os.path.join(here, "signed.pdf"), "wb").write(bytes(out))
open(os.path.join(here, "root.der"), "wb").write(run("openssl", "x509", "-in", "root.pem", "-outform", "DER"))
