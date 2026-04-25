# PolyForm Strict 1.0.0 as the default product license

Permissive licenses (MIT, Apache 2.0) let third parties resell
template-derived products without terms. Business Source License
(BUSL) was considered; PolyForm Strict was preferred because it has
no automatic conversion clause and no change-date tracking, which
keeps the licensing surface minimal for products that may never
open up.

Products can override the license during `./repo.sh initialize` or
by editing `LICENSE` and `.agents/repo.json:product.license`.
