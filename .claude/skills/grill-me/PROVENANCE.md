# Provenance: grill-me

| | |
|---|---|
| Upstream | https://github.com/mattpocock/skills |
| Author | Matt Pocock ([mattpocock.com](https://www.mattpocock.com)) |
| License | MIT (see `LICENSE`) |
| Upstream path | `skills/productivity/grill-me/SKILL.md` |
| Pinned commit | `3cca18b368ae95cdbdebbff572ccafa662551015` |
| Vendored in | 2026-09-12 |

The entry point. King types `/grill-me` and it hands straight to `grilling`. Its
frontmatter sets `disable-model-invocation: true`, so it never starts on its own.

## The pair travels together

`grill-me` is a seven line file whose whole job is to call `grilling`. Vendor one
without the other and the call resolves to nothing. Both live in `.claude/skills/`
in all fifteen of King's repos. Its partner here is `.claude/skills/grilling/`.

## Why this is vendored rather than installed

Upstream ships it as the `mattpocock-skills` plugin, listed in
`anthropics/claude-plugins-official`. That marketplace entry uses
`"source": "url"`, so installing it needs a second clone on top of the marketplace
fetch. A fresh cloud container never performs that clone, so `/grill-me` answered
"Unknown command" in web sessions while working on the Mac. A repo copy works in
every surface.

## Check for drift

```
git clone https://github.com/mattpocock/skills.git /tmp/mp
diff /tmp/mp/skills/productivity/grill-me/SKILL.md .claude/skills/grill-me/SKILL.md
```

No output means the copy matches upstream. Any output means upstream has moved;
read the change before taking it, then update the pinned commit above.
