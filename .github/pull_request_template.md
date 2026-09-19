## Summary

<!-- What changed and why -->

## Checklist

- [ ] Offline tests pass (`uv run pytest`)
- [ ] No secrets committed
- [ ] Auto-collect changes do not mark items curated
- [ ] Editorial fields preserved if touching existing resources

## Test plan

- [ ] `uv run jev-awesome validate`
- [ ] `uv run jev-awesome render --check`
