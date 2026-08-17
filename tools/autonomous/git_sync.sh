#!/usr/bin/env bash
# Shared git sync for anything on the VPS that commits to the repo.
#
# Three writers push to origin/main: the hourly autonomous session
# (dale-runner.sh), the hourly inbound-mail merge (merge-nursery-inbound.sh),
# and Benedict from his laptop. A rejected push is therefore normal and
# expected, not exceptional.
#
# It used to be handled by logging it and moving on. Both call sites said some
# version of "the commit is local and the next session will push it". Neither
# ever did, because the next session recovered with `git pull --ff-only`, which
# is precisely the one pull mode that cannot resolve a divergence. It exited 1
# and logged "git-pull-conflict". Three of those trip the 3-failure circuit
# breaker and autonomous Dale halts entirely.
#
# So one rejected push deadlocked all automation until a human intervened, and
# the failure surfaced an hour later pointing at git rather than at the push
# that caused it. On 2026-08-13 it ran for 50 minutes and was found by accident
# while auditing something unrelated.
#
# These two functions close that loop. A rejected push fetches, rebases and
# retries once. A session pull rebases its own unpushed work rather than giving
# up. Neither ever resolves a conflict: a real content conflict aborts cleanly
# and returns non-zero, because auto-merging the decision log unattended is a
# worse outcome than stopping and asking.
#
# Callers must be in the repo directory. Sourced, not executed.

# Set to 1 by git_sync_push / git_sync_pull when the operation only succeeded
# after rebasing. Callers should log that: a silent self-heal is how you end up
# not knowing the divergence is routine.
GIT_SYNC_REBASED=0

# True when the working tree has no uncommitted changes. We never rebase over
# uncommitted work; a stash-and-retry loop unattended is how data goes missing.
git_sync_is_clean() {
    [ -z "$(git status --porcelain 2>/dev/null)" ]
}

# Push to origin/main, healing a rejection caused by another writer.
#
# Exit codes:
#   0  pushed (check GIT_SYNC_REBASED to see whether it took a rebase)
#   1  working tree dirty, nothing attempted
#   2  fetch failed (network or auth)
#   3  rebase hit a real conflict, aborted, human needed
#   4  still rejected after a successful rebase (lost a second race)
git_sync_push() {
    local log_file="${1:-/dev/stderr}"
    GIT_SYNC_REBASED=0

    if git push -q origin main 2>>"$log_file"; then
        return 0
    fi

    if ! git_sync_is_clean; then
        return 1
    fi

    git fetch -q origin 2>>"$log_file" || return 2

    if ! git rebase origin/main >>"$log_file" 2>&1; then
        git rebase --abort >/dev/null 2>&1
        return 3
    fi

    GIT_SYNC_REBASED=1
    git push -q origin main 2>>"$log_file" || return 4
    return 0
}

# Bring the local repo up to date with origin/main before a session starts.
#
# Replaces a bare `git pull --ff-only`, which is right for a pure deploy target
# and wrong here: this box also pushes, so it can legitimately hold commits that
# origin does not.
#
# Exit codes:
#   0  up to date (check GIT_SYNC_REBASED to see whether it took a rebase)
#   1  working tree dirty, nothing attempted
#   2  ff-only failed for a reason other than our own unpushed commits
#   3  rebase hit a real conflict, aborted, human needed
git_sync_pull() {
    local log_file="${1:-/dev/stderr}"
    GIT_SYNC_REBASED=0

    git fetch -q origin 2>>"$log_file" || return 2

    # Skip the pull only when we already contain origin/main: equal, or ahead by
    # our own unpushed commits. The operands were the other way round, and
    # `--is-ancestor HEAD origin/main` is true precisely when we are BEHIND, so
    # the one case that exists to be fixed by a pull was the one case that
    # skipped it and returned success.
    if git merge-base --is-ancestor origin/main HEAD 2>/dev/null || \
       git pull --ff-only -q origin main 2>>"$log_file"; then
        return 0
    fi

    if ! git_sync_is_clean; then
        return 1
    fi

    # Only rebase when the divergence is our own unpushed commits. If ff-only
    # failed for any other reason, fail loudly rather than papering over it.
    if [ -z "$(git log origin/main..HEAD --oneline 2>/dev/null)" ]; then
        return 2
    fi

    if ! git rebase origin/main >>"$log_file" 2>&1; then
        git rebase --abort >/dev/null 2>&1
        return 3
    fi

    GIT_SYNC_REBASED=1
    return 0
}

# Human-readable reason for a git_sync_push / git_sync_pull exit code.
git_sync_explain() {
    case "$1" in
        0) echo "ok" ;;
        1) echo "working tree dirty, nothing attempted" ;;
        2) echo "fetch failed or non-divergence pull failure" ;;
        3) echo "rebase conflict, aborted, needs a human" ;;
        4) echo "still rejected after rebase, lost a second race" ;;
        *) echo "unknown status $1" ;;
    esac
}
