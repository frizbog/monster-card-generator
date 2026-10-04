# Custom monsters

The generator loads every `*.json` file recursively under this directory by
default, alongside the SRD repository. Files are read alphabetically by path.
Keep monster documents under `monsters/` (or another subfolder); no command-line
option is needed for the usual case.

```bash
python minisheets.py inspect-srd
python minisheets.py monster "Your Monster"
python minisheets.py roster rosters/your-roster.json
```

To use a different file or folder for a run, pass
`--custom-monsters /path/to/custom-folder` or
`--custom-monsters /path/to/one-document.json`.

## Adding a document that works

Each JSON file must be a complete document using the same `sections` format as
the SRD repository's `monsters-a-z.json` document. Existing files under
[`monsters/`](monsters/) are working examples and the safest starting points:
copy one or export another document in that format, then add your own stat-block
sections.

For each monster, the stat-block section needs:

- A `title` containing the monster's name.
- `content` (or `text`) containing its type line plus AC/Armor Class, HP/Hit
  Points, Speed, and CR/Challenge values.
- A `tables` entry containing the six ability scores, with `STR` present in the
  headers or rows.

Traits, Actions, Bonus Actions, Reactions, and Legendary Actions belong in
child sections whose `parentId` is the stat block's `id`. Give each child one of
those exact titles so the generator can recognize it.

Custom monsters override SRD monsters with the same name. Do not define the
same custom monster name in two files: the generator reports that as an error
so an accidental override cannot go unnoticed. Run `python minisheets.py inspect-srd`
after adding a document to confirm it is readable before rendering minisheets.
