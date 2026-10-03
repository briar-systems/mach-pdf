# write signed.pdf: golden/archive.pdf signed, filled and countersigned by pyhanko
#
# run from this directory with pyhanko 0.37:
#   python generate.py
# the signatures are not deterministic, so each run writes different bytes.
import time
from io import BytesIO

from pyhanko.pdf_utils import generic
from pyhanko.pdf_utils.generic import pdf_name
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.pdf_utils.writer import copy_into_new_writer
from pyhanko.sign import fields, signers

KEYS = '../sign/'


def signer(who):
    return signers.SimpleSigner.load(
        KEYS + who + '-key.pem', KEYS + who + '.pem', ca_chain_files=(KEYS + 'root.pem',)
    )


def prepare(data):
    # the page's /Annots moved into its own object, a text field that is its
    # own widget, and an empty signature field that locks every field but the
    # remark and witness fields once it is signed, written as one revision
    w = IncrementalPdfFileWriter(BytesIO(data))
    page_ref = w.root['/Pages']['/Kids'].raw_get(0)
    page = page_ref.get_object()
    annots = generic.ArrayObject(page['/Annots'])
    page['/Annots'] = w.add_object(annots)
    w.update_container(page)
    # the remark field draws with the reviewer field's font
    reviewer = next(f.get_object() for f in w.root['/AcroForm']['/Fields'] if f.get_object()['/T'] == 'reviewer')
    resources = reviewer['/Kids'][0].get_object()['/AP']['/N'].raw_get('/Resources')
    remark = w.add_object(generic.DictionaryObject({
        pdf_name('/Type'): pdf_name('/Annot'),
        pdf_name('/Subtype'): pdf_name('/Widget'),
        pdf_name('/FT'): pdf_name('/Tx'),
        pdf_name('/T'): generic.TextStringObject('remark'),
        pdf_name('/F'): generic.NumberObject(4),
        pdf_name('/P'): page_ref,
        pdf_name('/Rect'): generic.ArrayObject(generic.NumberObject(n) for n in (150, 440, 360, 460)),
        pdf_name('/DA'): generic.TextStringObject('/F1 12 Tf 0 g'),
        pdf_name('/AP'): generic.DictionaryObject({pdf_name('/N'): w.add_object(appearance(b'', resources))}),
    }))
    annots.append(remark)
    w.root['/AcroForm']['/Fields'].append(remark)
    w.update_container(w.root['/AcroForm'])
    author = fields.FieldMDPSpec(fields.FieldMDPAction.EXCLUDE, ['remark', 'witness'])
    fields.append_signature_field(w, fields.SigFieldSpec('author', box=(50, 60, 250, 110), field_mdp_spec=author))
    whole = copy_into_new_writer(PdfFileReader(BytesIO(written(w))))
    return written(whole)


def written(w):
    # pyhanko stamps each update's xmp metadata with the time to the second, so
    # waiting a second makes every update rewrite the stream
    time.sleep(1.1)
    out = BytesIO()
    w.write(out)
    return out.getvalue()


def sign(data, who, field, new=None, **meta):
    w = IncrementalPdfFileWriter(BytesIO(data))
    spec = signers.PdfSignatureMetadata(field_name=field, **meta)
    time.sleep(1.1)
    return signers.sign_pdf(w, spec, signer=signer(who), new_field_spec=new).getvalue()


def appearance(text, resources):
    stream = generic.StreamObject(
        {
            pdf_name('/Type'): pdf_name('/XObject'),
            pdf_name('/Subtype'): pdf_name('/Form'),
            pdf_name('/BBox'): generic.ArrayObject(generic.NumberObject(n) for n in (0, 0, 210, 20)),
            pdf_name('/Resources'): resources,
        },
        stream_data=b'/Tx BMC q BT /F1 12 Tf 0 g 2 6 Td (' + text + b') Tj ET Q EMC',
    )
    stream.compress()
    return stream


def fill(data):
    # the remark field's value, and its appearance stream rewritten in place
    w = IncrementalPdfFileWriter(BytesIO(data))
    listed = (f.get_object() for f in w.root['/AcroForm']['/Fields'])
    field = next(f for f in listed if f['/T'] == 'remark')
    field['/V'] = generic.TextStringObject('Approved')
    w.update_container(field)
    ref = field.raw_get('/AP').raw_get('/N').reference
    w.mark_update(ref)
    w.objects[(ref.generation, ref.idnum)] = appearance(b'Approved', ref.get_object().raw_get('/Resources'))
    return written(w)


with open('../../golden/archive.pdf', 'rb') as f:
    data = f.read()
data = prepare(data)
# the author certifies, permitting form filling and signing
data = sign(data, 'signer', 'author', certify=True, docmdp_permissions=fields.MDPPerm.FILL_FORMS)
data = fill(data)
# the witness signs a new invisible field, whose widget joins the page's
# /Annots array, and which locks the remark field
lock = fields.FieldMDPSpec(fields.FieldMDPAction.INCLUDE, ['remark'])
data = sign(data, 'witness', 'witness', new=fields.SigFieldSpec('witness', field_mdp_spec=lock))
with open('signed.pdf', 'wb') as f:
    f.write(data)
