# linkrot

Finds dead links in Markdown and HTML docs: URLs that 404, relative links to files that moved, and `#anchors` pointing at headings that were renamed.

```
$ linkrot docs/
docs/install.md:14: ../guide/setup.md (file not found)
docs/usage.md:31: #configuration (no heading #configuration)
docs/usage.md:52: https://example.com/old-page (HTTP 404)
212 links in 18 files, 3 broken (1.4s)
```

No dependencies beyond the Python standard library.

## Install

```sh
pipx install git+https://github.com/Shabfom/linkrot
```

or run it from a checkout with `python -m linkrot` (with `src` on `PYTHONPATH`).

## Usage

```sh
linkrot                      # everything under the current directory
linkrot README.md docs/      # specific files and folders
linkrot --offline            # skip the network, check local files and anchors only
linkrot --ignore 'http://localhost*' --ignore 'https://example.com/*'
linkrot --json               # machine-readable output
```

It exits with 1 when something is broken, so it works as a CI step:

```yaml
- run: pipx run --spec git+https://github.com/Shabfom/linkrot linkrot --offline
```

### What gets checked

- Markdown inline links and images, reference definitions (`[id]: url`), `<autolinks>` and raw HTML `href`/`src`. Links inside code blocks and inline code are ignored.
- Relative paths are checked against the file system. `#fragments` are matched against headings using GitHub's anchor rules (including the `-1`, `-2` suffixes for repeated headings) and explicit `id`/`name` attributes.
- External URLs get a `HEAD` request, then a `GET` if the server refuses `HEAD`. Each URL is requested once no matter how many files use it. 5xx and 429 responses are retried once.
- 401, 403 and 429 are reported but don't fail the run, because sites behind bot protection send them to scripts even when the page is fine. Use `--strict` to fail on them too.
- `node_modules`, `.git`, virtualenvs and build output folders are skipped.

## Development

```sh
PYTHONPATH=src python -m unittest discover -s tests
```

The tests start a throwaway local HTTP server, so they don't need network access.

## License

MIT
