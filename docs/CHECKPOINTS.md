# Checkpoint workflow

Rule: **`main` always works.** A stuck phase never damages finished progress.

## How each task runs

1. Branch from `main`: `git switch -c task/NN-short-name`
2. Commit as often as you like on the branch (WIP commits are fine).
3. Done = all tests green (`pytest`) + the checkpoint's acceptance criteria met.
4. Merge into `main` with `--no-ff` (keeps the task visible as one unit in history).
5. Tag the merge: `git tag -a cp-NN -m "<summary>"` and push tags.
6. Log it in the table below.

## If we get stuck

- Leave the branch as is — nothing on `main` is touched.
- Start over from the last good state: `git switch main && git switch -c task/NN-retry`
- Inspect any past checkpoint: `git switch --detach cp-NN`
- Roll `main` back (only if a merged checkpoint turns out broken): `git revert -m 1 <merge-commit>`
  — never `reset --hard` on a pushed `main`.

## Log

| Tag   | Task                                   | Date       | Tests |
|-------|----------------------------------------|------------|-------|
| cp-00 | Repo scaffold + checkpoint workflow    | 2026-10-10 | n/a   |
| cp-01 | Shared Pydantic schemas (gen 1-4 aware) | 2026-10-10 | 35 passed |
| cp-02 | Dex data layer, Gens 1-4 (`@pkmn/dex` snapshot) | 2026-10-10 | 68 passed |
