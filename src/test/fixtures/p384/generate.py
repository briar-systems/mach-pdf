# write signed.pdf and root.der: a minimal pdf signed with a p-384 key and sha-256,
# as okular signs with a yubikey
#
# run from this directory with openssl 3.4 or later and python 3:
#   python3 generate.py
# the root's key is thrown away. the signature is not deterministic, so each
# run writes different bytes.
import os
import subprocess
import tempfile

SLOT = 2048


def openssl(*args, data=None):
    return subprocess.run(['openssl', *args], input=data, check=True, capture_output=True).stdout


def objects(contents, byte_range):
    return [
        '<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [4 0 R] /SigFlags 3 >> >>',
        '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Annots [4 0 R] >>',
        '<< /Type /Annot /Subtype /Widget /FT /Sig /T (signature) /Rect [0 0 0 0] /F 132 /P 3 0 R /V 5 0 R >>',
        '<< /Type /Sig /Filter /Adobe.PPKLite /SubFilter /adbe.pkcs7.detached /ByteRange ' + byte_range
        + ' /Contents <' + contents + '> >>',
    ]


def build(contents, byte_range):
    out = b'%PDF-1.7\n'
    offsets = []
    for n, body in enumerate(objects(contents, byte_range), 1):
        offsets.append(len(out))
        out += ('%d 0 obj\n%s\nendobj\n' % (n, body)).encode()
    xref = len(out)
    out += ('xref\n0 6\n0000000000 65535 f \n' + ''.join('%010d 00000 n \n' % o for o in offsets)).encode()
    out += ('trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % xref).encode()
    return out


with tempfile.TemporaryDirectory() as work:
    def path(name):
        return os.path.join(work, name)

    openssl('genpkey', '-algorithm', 'EC', '-pkeyopt', 'ec_paramgen_curve:P-384', '-out', path('root.key'))
    openssl('req', '-x509', '-new', '-key', path('root.key'), '-sha384', '-subj', '/O=mach-pdf/CN=mach-pdf p384 root',
            '-not_before', '20260101000000Z', '-not_after', '20460101000000Z',
            '-addext', 'basicConstraints=critical,CA:TRUE', '-addext', 'keyUsage=critical,keyCertSign,cRLSign',
            '-addext', 'subjectKeyIdentifier=hash', '-out', path('root.pem'))
    openssl('x509', '-in', path('root.pem'), '-outform', 'DER', '-out', 'root.der')

    openssl('genpkey', '-algorithm', 'EC', '-pkeyopt', 'ec_paramgen_curve:P-384', '-out', path('leaf.key'))
    openssl('req', '-new', '-key', path('leaf.key'), '-subj', '/O=mach-pdf/CN=mach-pdf p384 signer', '-out', path('leaf.csr'))
    with open(path('leaf.ext'), 'w') as f:
        f.write('basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,nonRepudiation\n'
                'subjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid\n')
    openssl('x509', '-req', '-in', path('leaf.csr'), '-CA', path('root.pem'), '-CAkey', path('root.key'), '-sha384',
            '-not_before', '20260101000000Z', '-not_after', '20460101000000Z',
            '-set_serial', '0x' + openssl('rand', '-hex', '8').decode().strip(), '-extfile', path('leaf.ext'),
            '-out', path('leaf.pem'))

    # a fixed-width byte range, then the cms over everything outside the contents
    blank = build('0' * (2 * SLOT), '[0 0000000000 0000000000 0000000000]')
    start = blank.index(b'<' + b'0' * 16) + 1
    end = start + 2 * SLOT
    byte_range = '[0 %010d %010d %010d]' % (start - 1, end + 1, len(blank) - end - 1)
    data = build('0' * (2 * SLOT), byte_range)
    signed = data[:start - 1] + data[end + 1:]
    cms = openssl('cms', '-sign', '-binary', '-md', 'sha256', '-signer', path('leaf.pem'), '-inkey', path('leaf.key'),
                  '-outform', 'DER', '-nosmimecap', data=signed)
    assert len(cms) <= SLOT
    hexed = cms.hex().upper().ljust(2 * SLOT, '0')
    with open('signed.pdf', 'wb') as f:
        f.write(data[:start] + hexed.encode() + data[end:])
