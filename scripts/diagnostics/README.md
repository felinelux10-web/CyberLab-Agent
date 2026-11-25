# CyberLab Agent diagnostics

These utilities are intentionally separated from normal agent startup.

## Read-only checks

- `device_profile.py` reports Android/Termux runtime, memory, storage, Python and SQLite capabilities.
- `benchmark_conversation_fts.py` measures legacy FTS5 and LIKE search. It opens the database read-only. If the normalized index has been explicitly rebuilt, it also measures normalized FTS5.
- `evaluate_saved_dialogue.py` runs ten evidence/abstention checks against a saved dialogue. By default it targets the previously investigated session 72; pass `--session-id` to select another dialogue.
- `audit_memory_store.py` checks SQLite integrity, duplicate exchange rows, fact-source links, temporal metadata consistency and normalized-index completeness. It is read-only.

## Explicit derived-index rebuild

`rebuild_normalized_fts.py` is the only write-enabled diagnostic in this directory. It requires `--confirm`, writes only the derived normalized FTS5 index and its migration marker, and does not update or delete source messages or the legacy FTS index. It processes at most 200 messages per batch by default.

Run the device profile and read-only benchmark before rebuilding. On Android, perform the rebuild while the phone is charging and Termux is kept awake. The operation is restartable: if interrupted, run it again; it rebuilds the derived index from the source message table.

No diagnostic runs automatically during agent startup.
