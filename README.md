# mach-pdf

PDF for Mach (ISO 32000-2): an object model and a deterministic writer, with
incremental updates and reserved spans for values written after the fact. It
is a spec implementation with no knowledge of any document format above it,
and it depends on mach-std only.

## Modules

- `pdf.object` is the object model: null, booleans, integers, decimal reals,
  strings, names, arrays, dictionaries, streams, indirect references, and
  `Reserved` spans. Objects live in the allocator they were built with and copy
  what they are given.
- `pdf.filter` is the stream filter contract. A stream lists its filters in
  decode order and the writer encodes through them. `ascii_hex` is the one
  encoder so far; FlateDecode drops in as another `Filter` once std has a
  deflate compressor.
- `pdf.document` numbers indirect objects, owns them in an arena, and saves
  the whole file (`save`) or an incremental update of what changed since
  (`append`), with a cross-reference table or stream. `rebase` starts from a
  revision read from a file.
- `pdf.syntax` spells objects as bytes and fills a written reservation in
  place.
- `pdf.output` is the file image the writer produces, kept in memory so every
  byte offset is known.
- `pdf.content` writes content stream operators: graphics state, paths, fill
  and stroke, text positioning, font selection, strings and glyph runs.
- `pdf.page` builds the page tree, pages, their content and font resources.
- `pdf.font` adds standard 14 font dictionaries.
- `pdf.text` makes text strings from utf-8, as ascii when it can and utf-16be
  otherwise.
- `pdf.date` spells a caller's date as a pdf date string or an xmp date.
- `pdf.metadata` writes the information dictionary and the xmp metadata
  stream together from one description, with extra xmp claims such as a
  conformance level's.
- `pdf.embed` attaches files: an embedded file stream, its file
  specification with its `/AFRelationship`, the catalog's `/EmbeddedFiles`
  name tree and its `/AF` array.
- `pdf.pdfa` makes a document pdf/a-3b (see below).
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

## PDF/A-3b

`pdfa.conform` writes the metadata with the pdf/a-3b identification, adds an
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

## Signatures and other late values

A `Reserved` object writes a fixed-width placeholder and records its byte
offset when it is saved. Once the file is written, `syntax.fill` puts the real
value in its place, padded with spaces. A signature reserves its `/Contents`
and `/ByteRange` this way, computes the byte range from the recorded offsets,
and fills both after hashing.

## Build

```sh
mach dep pull .
mach build .
mach test . --all --timeout 5m
```

`demo/sample` writes the sample document to two files and the pdf/a-3b sample
to a third, the golden files the tests compare against. Check them with `qpdf --check` and a renderer
(`pdftoppm`, `mutool`, pdf.js) after any change to the output:

```sh
cd demo/sample
mach dep pull .
mach build .
./out/linux-x86_64/debug/bin/sample ../../src/test/golden/table.pdf ../../src/test/golden/stream.pdf ../../src/test/golden/archive.pdf
```

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
