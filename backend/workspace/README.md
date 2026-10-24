# Agent workspace

Each account has a private folder here, `user-<id>`: the files its agents can
list, search and read, and the files its owner sees, uploads and downloads on
the Files page. Agents can also save new `.txt`, `.md`, `.json`, `.csv`, `.html`,
`.docx` and `.pdf` artifacts, but cannot overwrite existing files or reach
hidden paths. The folder is bounded by `WORKSPACE_MAX_TOTAL_BYTES`. When
`run_python` is enabled, the files its code writes and the charts it displays
are saved under `sandbox/<UTC time>/` in that folder, with the same rules.
