# the fuzz lane

`corpus/<boundary>/` holds the retained inputs for every untrusted-input entry
point of the library. Each directory pairs with a row of the registry in
`src/boundaries.mach`, which names the harness that answers it:

| boundary | entry point |
|---|---|
| `reader` | `reader.read`, then `document.load` on every number, `document.decoded` on every stream a built-in filter decodes, and an update appended and read back |

## Answers

An input is answered when the reader reads it or refuses it with a typed
error. A file it accepts must also take an update: the harness sets a key in
the catalog, appends the update with `document.append`, and reads the result
back, which must succeed and hold the key. Breaking that is a finding.

Each input is copied so that it ends on the last byte before an unreadable page
(`std.allocator.testing`), so a parser that reads one byte past its input
faults on the spot. A crash is a finding. So is a hang: every walk the reader
makes is bounded by its input and its options, and the replay runs under a
timeout. The harness tightens the reader's bounds (`src/reader.mach`) so a
mutated `/Size` or a decompression bomb is answered quickly.

## Running it

From the repository root:

```sh
mach dep pull test/fuzz
mach build test/fuzz
test/fuzz/out/linux-x86_64/debug/bin/fuzz replay
test/fuzz/out/linux-x86_64/debug/bin/fuzz one <boundary> <file>
test/fuzz/out/linux-x86_64/debug/bin/fuzz mutate <boundary|all> <runs> <seed> [--retain]
```

`replay` answers every retained input and fails on a finding, on an empty
boundary directory, or on a directory no boundary answers. Run it in both
profiles before a change to the reader or the parser lands.

`mutate` is the on-demand search. It draws from a boundary's corpus, applies one
to three structural mutations (flip a bit, set a byte, truncate, extend, swap,
zero a run) from one seeded generator, and answers the result, so a seed and a
run count replay exactly. A finding is written to
`test/fuzz/out/findings/<boundary>/`. With `--retain`, an input whose outcome
the corpus does not hold yet is minimized, by cutting ever smaller chunks while
the outcome holds, and written to its boundary's directory as `m-<outcome>.bin`.

An outcome is what the read answered: the failure it refused the file with, or
for an accepted file the set of failures its objects and streams met, how many
of each it read, its cross-reference form, and how the update went. This is
not code coverage. There is no coverage instrumentation for Mach, so two inputs
that reach different code with the same answer count as one.

## The corpus

The named `.pdf` files are the writer's golden files and the reader's fixtures
(`src/test/fixtures/read`), each accepted by the reader. The `s-*.pdf` files
are hostile by construction, written by `seeds.py`: deep nesting, a `/Prev`
loop, a stream whose `/Length` is itself, a decompression bomb, and an object
stream that claims its own objects. The `m-*` files were retained by mutation.

To retain a new input by hand, put the file in its boundary's directory. When a
finding is fixed, retain the input that found it, so the replay keeps it fixed.
