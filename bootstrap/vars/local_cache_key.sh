# repo CI .local/ cache key.
#
# GitHub Actions hashes this file and .agents/repo.json, not repo.sh. Keep
# this file focused on changes that should invalidate reusable bootstrap state.
# Editing command dispatch, docs, hooks, or messages should not cold-start CI.

cache_epoch=1
bootstrap_artifact_format=1
