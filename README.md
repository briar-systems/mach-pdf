# mach-pdf

PDF for Mach (ISO 32000-2): an object model, a deterministic writer and a
reader, with incremental updates and reserved spans for values written after
the fact, and PAdES signatures. It is a spec implementation with no knowledge of any document format above it,
and it depends on mach-std and mach-font. Only `pdf.sign` and `pdf.verify` use mach-pki, so a program that does not import them links no pki or crypto code.

## Modules

- `pdf.object` is the object model: null, booleans, integers, decimal reals,
  strings, names, arrays, dictionaries, streams, indirect references, and
  `Reserved` spans. Objects live in the allocator they were built with and copy
  what they are given.
- `pdf.filter` is the stream filter contract. A stream lists its filters in
  decode order, the writer encodes through them and `document.decoded` decodes
  through them. `ascii_hex` encodes and decodes. `flate` encodes a zlib stream
  through `std.compress.deflate` at `filter.FLATE_LEVEL` (6) with no
  predictor, and decodes zlib data through `std.compress.zlib`, undoing PNG and
  TIFF predictors. A decoder is given its decode
  parameters with their references resolved and a limit on what it may
  produce.
- `pdf.document` numbers indirect objects, owns them in an arena, and saves
  the whole file (`save`) or an incremental update of what changed since
  (`append`), with a cross-reference table or stream. `rebase` starts from a
  revision read from a file, and a `Source` loads that revision's objects the
  first time `resolve` or `load` meets them.
- `pdf.parse` reads objects from bytes into the object model.
- `pdf.reader` reads a file into a document (see below).
- `pdf.syntax` spells objects as bytes and fills a written reservation in
  place.
- `pdf.output` is the file image the writer produces, kept in memory so every
  byte offset is known.
- `pdf.content` writes content stream operators: graphics state, paths, fill
  and stroke, text positioning, font selection, strings and glyph runs.
- `pdf.page` builds the page tree, pages, their content and font resources.
- `pdf.font` adds standard 14 font dictionaries, and embeds TrueType faces as
  subsets (see below).
- `pdf.text` writes text strings: ascii as it is, anything else as utf-16be.
- `pdf.form` builds an AcroForm: groups, text, date and unsigned signature
  fields, and their widgets with appearance streams.
- `pdf.date` spells a caller's date as a pdf date string or an xmp date.
- `pdf.metadata` writes the information dictionary and the xmp metadata
  stream together from one description, with extra xmp properties from the
  caller (`props`) and claims the writer adds, such as a conformance level's.
- `pdf.embed` attaches files: an embedded file stream, its file
  specification with its `/AFRelationship`, the catalog's `/EmbeddedFiles`
  name tree and its `/AF` array.
- `pdf.pdfa` makes a document pdf/a-3b (see below).
- `pdf.sign` signs a signature field as an incremental update, PAdES B-B
  (see below).
- `pdf.verify` verifies every signature in a file and judges each later
  update (see below).
- `pdf.error` is the failure every module reports.

`use pdf;` binds `pdf.lib.pdf`, which re-exports these modules.

## Use

```mach
use pdf.content;
use pdf.document;
use pdf.error;
use pdf.font;
use pdf.object;
use pdf.output;
use pdf.page;

# write a one-page document into out, drawing on the allocator a
fun hello(a: *allocator.Allocator, out: *output.Output) err[error.Error] {
    var doc: document.Document;
    val started: err[error.Error] = document.init(?doc, a);
    if (sel started.err) { ret started; }
    fin { document.dnit(?doc); }

    val tree: res[page.Tree, error.Error] = page.tree(?doc);
    if (sel tree.err) { ret err[error.Error].err{tree.err}; }
    var pages: page.Tree = tree.ok;
    val helvetica: res[object.Ref, error.Error] = font.standard(?doc, "Helvetica");
    if (sel helvetica.err) { ret err[error.Error].err{helvetica.err}; }
    val added: res[page.Page, error.Error] = page.add(?doc, ?pages, page.A4);
    if (sel added.err) { ret err[error.Error].err{added.err}; }
    var p: page.Page = added.ok;
    val fonts: err[error.Error] = page.use_font(?doc, ?p, "F1", helvetica.ok);
    if (sel fonts.err) { ret fonts; }

    val started_content: res[content.Builder, error.Error] = page.contents(?doc, ?p);
    if (sel started_content.err) { ret err[error.Error].err{started_content.err}; }
    var b: content.Builder = started_content.ok;
    content.begin_text(?b);
    content.font(?b, "F1", 12.0);
    content.move_text(?b, 72.0, 770.0);
    content.show_text(?b, "Hello");
    content.end_text(?b);
    val finished: err[error.Error] = content.finish(?b);
    if (sel finished.err) { ret finished; }

    # out then holds output.offset(out) bytes of pdf at output.data(out)
    ret document.save(?doc, out);
}
```

## Determinism

The same objects built in the same order give the same bytes on every host.
Nothing time or host dependent is written: no dates unless the caller gives
them, and no `/ID` unless the caller sets one with `document.set_id`. Reals are decimals rounded half away
from zero, and every object has exactly one spelling. The tests compare the
sample document in `src/test/sample.mach` byte for byte against the files in
`src/test/golden/`, in both cross-reference forms, and the pdf/a-3b sample in
`src/test/archive.mach` likewise.

Streams the library builds are compressed with FlateDecode: content streams
and appearance streams, font programs, `/CIDToGIDMap` and `/ToUnicode`
streams, the icc profile, embedded files and cross-reference streams
(`doc.xref_filters` starts with it). The compressor's output depends only on
its input, the level and the zlib container, and the level is the one fixed
`filter.FLATE_LEVEL`, so compression keeps every file byte for byte the same.
The xmp metadata stream stays uncompressed, so a tool that does not read pdf
can still find the packet, as the xmp specification (part 3) recommends. ISO 19005-3 allows a filter there but pdf/a-1 forbade one, and
`pdfa.check` keeps requiring none.

## PDF/A-3b

`pdfa.conform` writes the metadata once, the caller's description and its extra
xmp properties (`meta.props`) with the pdf/a-3b identification, adds an
srgb output intent with its icc profile embedded, and has every later save run
`pdfa.check` first through `document.require`. The check refuses, as
`nonconforming` naming the offending object, unembedded fonts, encryption,
javascript and the other actions pdf/a forbids, and content outside the file,
and it requires an `/ID`, the metadata, the output intent and every embedded
file associated through an `/AF` array. The caller sets the `/ID`, embeds its
fonts and attaches files with `embed.attach`:

```mach
var meta: metadata.Metadata;
meta.title    = "Report";
meta.producer = "mach-pdf";
var id: metadata.Claim = metadata.Claim{prefix: "dc", uri: "http://purl.org/dc/elements/1.1/",
    property: "identifier", value: "REP-1"};
meta.props     = ?id;
meta.props_len = 1;
val made: err[error.Error] = pdfa.conform(?doc, ?meta);
var source: embed.File = embed.File{name: "report.txt", data: text, len: len,
    mime: "text/plain", relationship: embed.Relationship.source{},
    description: nil, modified: opt[date.Date].none{}};
val attached: res[object.Ref, error.Error] = embed.attach(?doc, ?source);
val identified: err[error.Error] = document.set_id(?doc, id, 16, id, 16);
```

Nothing is implied: no dates, identifiers or tool names the caller did not
give. `src/test/archive.mach` builds a sample that `src/test/golden/archive.pdf`
holds, and [veraPDF](https://verapdf.org) validates that file as pdf/a-3b
(`verapdf --flavour 3b archive.pdf`). veraPDF is a local check, not a CI one.

## Forms

`form.init` gives the catalog an `/AcroForm` whose values are drawn in a
`form.Face`. A group only names the fields under it, so `group(nil, "owner")`
then `text_field(?owner, "name")` is the field `owner.name`. A terminal field
keeps its widgets as kids, never merged into it: `form.widget` places another
one on a page, and a value entered in any of them shows in all of them.

Every widget is written the way PDF/A asks: a normal appearance stream, the
print flag, and no `/NeedAppearances`, actions or JavaScript. An appearance
draws only the value, with no background or border, so whatever the page draws
beneath a widget, such as the dots of a blank, shows through.

A date field is a text field. PDF formats dates through JavaScript actions,
which PDF/A forbids, so a date field puts its expected format in its tooltip
(`Date signed (YYYY-MM-DD)`) and leaves the entry to the viewer.

A signature field is written unsigned, with no `/V`. Signing it is an
incremental update that gives the field's dictionary (`Field.node`) a `/V`.
`form.terminals` reads every terminal field of a document's field tree, such
as one read from a file, with its fully qualified name and inherited `/FT`, and
`form.find` the one a name names.

`form.standard` is a face over a standard 14 font, which needs no embedding but
is not allowed in PDF/A. `form.embedded` is a face over an embedded TrueType
subset, which PDF/A allows: it writes Identity-H glyph codes and refuses a
character the face has no glyph for. Every value must be set before the face is
embedded.

## Embedded fonts

`font.truetype` starts embedding a TrueType face, parsed and subset by
[mach-font](https://github.com/briar-systems/mach-font). `font.show` writes
UTF-8 text in it as two-byte codes, giving each distinct code point the next
cid in order of first use, and `font.embed` writes the font once the text is
done: a Type0 font with Identity-H encoding over a CIDFontType2 descendant, the
subset holding only the glyphs the text reaches (composite components
included), a `/CIDToGIDMap`, `/W` widths, a `FontDescriptor` with the program
as `/FontFile2`, and a `/ToUnicode` cmap, so text extracts as it was written.
The subset tag comes from a digest of the subset, so the same document gives
the same bytes. A code point the face has no glyph for is the error `glyph`
naming it, never a silent `.notdef`.

```mach
val mono: res[*font.TrueType, error.Error] = font.truetype(?doc, data, len);
page.use_font(?doc, ?p, "F1", mono.ok.font);
content.font(?b, "F1", 11.0);
font.show(?b, mono.ok, "Grüße, Ζεύς");
content.finish(?b);
val embedded: err[error.Error] = font.embed(mono.ok);
```

`src/test/fonts.mach` sets Latin, accented, Cyrillic and Greek text in
Liberation Mono (`src/test/fixtures/liberation`, SIL OFL 1.1), and the PDF/A-3b
sample sets its text and form field in it too.

## Signatures and other late values

A `Reserved` object writes a fixed-width placeholder and records its byte
offset when it is saved. Once the file is written, `syntax.fill` puts the real
value in its place, padded with spaces.

`sign.sign` signs an unsigned signature field of a document read from a file,
PAdES baseline B-B (ETSI EN 319 142-1). It appends an update giving the field
a signature dictionary as its `/V` (`/Filter /Adobe.PPKLite`, `/SubFilter
/ETSI.CAdES.detached`, `/M` when the caller gives a time) and marks the form
append-only. The dictionary's `/ByteRange` and `/Contents` are reservations,
`/Contents` sized to the signed data the signer can make, measured before it
signs. Once the update is written the byte range is filled, the bytes either
side of `/Contents` are hashed, and the detached CMS signed data mach-pki builds
over that digest, with signing-certificate-v2 and no signing-time, is filled
into `/Contents`. The signer is mach-pki's signer contract, so a key in memory,
a token or a remote service signs the same way. Nothing reads a clock, so the
same file, field, time and a deterministic signer give the same bytes.

```mach
var doc: document.Document;
document.init(?doc, a);
reader.read(?doc, data, len, reader.defaults());
var out: output.Output = output.init(a);
output.put(?out, data, len);
# value is an open signer.Signer, such as key_signer.signer(?keyed)
var spec: sign.Spec = sign.Spec{field: "owner.signature", signer: ?value,
    algorithm: x509.SIGNATURE_NONE, time: opt[date.Date].some{now}};
val signed: err[sign.Error] = sign.sign(?doc, ?out, ?spec);
```

B-T and B-LT build on the same path. B-T attaches an RFC 3161 time-stamp
token over the signature with `cms.attach_unsigned` before `/Contents` is
filled, with the reservation grown by the token's size. B-LT is a later update
adding the catalog's `/DSS` with certificates, OCSP responses and CRLs, and a
document time-stamp is one more signature dictionary of `/Type
/DocTimeStamp`. Verification already allows both kinds of update.

`verify.verify` reads a file's revisions (`reader.history`) and judges every
signed signature field: its byte range starts the file, leaves out exactly its
`/Contents` string and ends where a revision ends, its signed data verifies
over that range with its certificate path validated against the caller's trust
store, and every later update changes only what the document permits. An
update may add objects, and may change the catalog's `/DSS` and
`/Extensions`, the security store, the form's `/SigFlags`, `/DR` and new
signature fields, a field's or widget's `/V`, `/AP` and `/AS` (a signature's
`/V` only from absent), a page's `/Annots` and the annotations on it. A
certifying signature's `/DocMDP` permission narrows that: 1 allows only the
security store, 2 adds form filling and signing, and 3 or no `/DocMDP` adds
annotations. Field locks are not read. `verify.valid` says whether a signature
passed every check, and the report keeps each check and each update's verdict.

`src/test/signatures.mach` signs the sample form, and a form with two
signature fields by two signers in turn, compares both with the golden files,
verifies them, and checks that a byte changed after signing and an update
changing the catalog are caught. The signers are the P-256 test keys in
`src/test/fixtures/sign` (`generate.sh` remakes them), whose RFC 6979
signatures are deterministic.

## Reading

`reader.read` parses the header, the cross-reference tables and streams back
through the `/Prev` chain, hybrid files' `/XRefStm`, and the last trailer's
`/Root`, `/Info` and `/ID`. It rebases the document on the file, so objects
load from the file the first time they are resolved, object streams decode the
first time one of their objects is, and the next save appends an incremental
update after the file's bytes:

```mach
var doc: document.Document;
document.init(?doc, a);
val read: err[error.Error] = reader.read(?doc, data, len, reader.defaults());
val root: res[*object.Dict, error.Error] = document.catalog(?doc);
object.set(root.ok, "Lang", lang);
document.touch(?doc, doc.root.some);
# out starts with the file's len bytes at data
val updated: err[error.Error] = document.append(?doc, ?out);
```

The file's bytes stay the caller's, and stay put until the document is done.
`document.resolve` gives the object a reference names, `document.deref`
follows a value that may be a reference, `document.load` gives the object a
number holds whatever its generation, and `document.decoded` gives a stream's
data with its filters undone. A stream read from a file keeps its data encoded
under its filters, so an update that rewrites it copies it as it was. A filter
this library has no decoder for keeps its name, and decoding through it is
`decoder`. A caller adds decoders through `reader.Options.filters`.

Reading is strict unless `reader.Options.strict` is false, which accepts a
header after leading bytes, a missing `%%EOF`, a stream whose `/Length` is
wrong, a key a dictionary holds twice (the last value wins), and loose
cross-reference table rows. Either way the reader is bounded for hostile files:
`max_depth` bounds nesting and loads inside loads, `max_objects` the highest
`/Size`, `max_decoded` what a cross-reference or object stream decodes to, and
`max_revisions` the `/Prev` chain. A file past a bound is `limit`, broken
syntax is `malformed` with its byte offset, an object whose loading needs its
own value is `cycle`, and an encrypted file is `encrypted`.

`src/test/read.mach` reads every file the writer produces and the files in
`src/test/fixtures/read` that Chrome's print to PDF, LibreOffice and pdfTeX
wrote, plus a hand-built hybrid file, walks every object and stream, appends an
update and reads it back.

The fuzz lane in `test/fuzz` mutates a retained corpus of files and reads
each, looking for a fault, a hang, or an accepted file that does not read back
once updated. It runs locally, not in CI (see `test/fuzz/README.md`).

## Build

```sh
mach dep pull .
mach build .
mach test . --all --timeout 5m
```

`demo/sample` writes the sample document to two files, the pdf/a-3b sample to
a third and the embedded font sample to a fourth, `demo/fields` the sample form to one, and
`demo/sign` the signed samples to two, the golden files the tests compare against. Check them with `qpdf --check` and a renderer
(`pdftoppm`, `mutool`, pdf.js) after any change to the output:

```sh
cd demo/sample
mach dep pull .
mach build .
./out/linux-x86_64/debug/bin/sample ../../src/test/golden/table.pdf ../../src/test/golden/stream.pdf ../../src/test/golden/archive.pdf ../../src/test/golden/fonts.pdf
```

The sample form should also fill in a viewer with a form API, such as MuPDF
(`pymupdf`) or pdf.js: entering `owner.name` in one widget shows it in both.

Check the signed samples with poppler's `pdfsig`, pyHanko
(`pyhanko sign validate --trust src/test/fixtures/sign/root.pem`), EU DSS and
Acrobat Reader with the test root trusted. These are local checks, not CI ones.

## Workflow

`dev` is the default branch. Work branches from it as `feat/<issue>` or
`fix/<issue>` and merges back through a pull request. `main` only takes release
merges from `dev`. A `hotfix/<issue>` branches from `main` and merges into both.

Both branches require a pull request and a passing `gate` check. Neither can be
deleted or force-pushed, and pull requests merge with a merge commit. Repository
admins can bypass these rules to cut a release. Once a `v*` tag is pushed, only
an admin can move or delete it.

Commits follow [Conventional Commits](https://www.conventionalcommits.org), with
the issue number as the scope: `fix(#12): reject a negative length`.

Issues are labeled on independent axes:

| axis | labels |
| --- | --- |
| semver magnitude | `patch`, `minor`, `major` |
| kind of work | `feature`, `fix`, `removal`, `chore`, `performance` |
| where, omitted for core code | `testing`, `tooling`, `doc` |
| severity and state | `critical`, `blocked`, `parked`, `security` |
| discussion | `discussion` |

## CI

`.github/workflows/ci.yml` runs on pull requests, on Linux. It checks formatting,
builds every artifact for every target in `mach.toml`, and runs the unit tests of
the targets the runner can execute. Targets no runner executes, such as riscv, are
built, never tested. Nothing runs under emulation.

To test on other hosts before merging, such as a darwin-specific change, dispatch
it on the branch: `gh workflow run CI --ref <branch> -f runners='["macos-15"]'`.
A project whose primary host is not Linux changes the default runner list in the
`test` job's matrix.

CI checks that the project builds and its unit tests pass. Integration, load or
demo suites are not CI jobs. Run them locally.

`gate` is the check the branch rules require. It fails if any job it needs
failed or was cancelled.

The compiler version is `MACH_VERSION`, an exact release, in `ci.yml` and
`cd.yml`. Change it together with the `mach` range in `mach.toml`.

## Releases

1. Set `version` in `mach.toml` and merge that into `dev`.
2. Merge `dev` into `main`.
3. Tag `main` and push the tag: `git tag vX.Y.Z && git push origin vX.Y.Z`.

`.github/workflows/cd.yml` checks that the tag matches the manifest version,
runs CI in the release profile on every host the project ships to (the
`runners` list in `cd.yml`, trimmed to the targets it declares), cross-builds
every artifact for every target in release, and publishes a GitHub release. Each artifact is packaged per target
(`.zip` for Windows, `.tar.gz` elsewhere) with `SHA256SUMS`. Names and paths come
from `mach build --plan`, so a new target or artifact needs no workflow change.
The notes are the version's `CHANGELOG.md` section, or generated from merged pull
requests when there is none. A tag with a prerelease part, such as `v1.0.0-rc.1`,
is published as a prerelease.

## License

MIT. See [LICENSE](LICENSE). The srgb profile in `src/icc` is from
[Compact-ICC-Profiles](https://github.com/saucecontrol/Compact-ICC-Profiles)
and in the public domain under CC0, see [src/icc/LICENSE](src/icc/LICENSE).
