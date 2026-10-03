#!/usr/bin/env python3
# writes signed.pdf: a page with two empty signature fields, "first" and
# "second", each a field with one widget kid whose appearance is an empty
# stream, then two incremental updates that each sign one field the way okular
# 25.08 does. the update rewrites the field to hold /V, the widget to gain /M,
# /Border and /AS with a new appearance stream, and the acroform to set
# /SigFlags, and adds the signature dictionary. the signatures' /Contents are
# zeros, so the file exercises the update judge and not signature checks.
# run: python3 generate.py > signed.pdf

import sys

out = bytearray()
xref = {}
GAP = 64


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
    return at

# each update's cross-reference section lists only what it writes
xref.clear()
second = sign(6, 8, 7, 12, "first", 600, first, True)
xref.clear()
third = sign(9, 11, 10, 13, "second", 500, second, False)
sys.stdout.buffer.write(bytes(out))
