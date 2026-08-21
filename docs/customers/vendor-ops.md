# Vendor ops (while IP paper is outstanding)

Do this work **without** invoicing. [ip-assignment.md](ip-assignment.md) is
still required before the first quote.

## This week (CTO on PTO)

1. Confirm `licensing@opsdevcode.com` delivers (forward to you).
2. Practice issuing a **non-customer** file you never send:

   ```bash
   python3 scripts/issue_repave_license.py \
     --organization opsdevcode-internal \
     --sku pilot \
     --expires 2026-11-21 \
     --out /tmp/repave-internal-pilot.json
   ```

3. List GHCR packages you will grant later (do **not** add third-party readers yet):

   - `ghcr.io/opsdevcode/repave-engine`
   - `ghcr.io/opsdevcode/repave-engine-portal`
   - `ghcr.io/opsdevcode/repave-corpus`
   - `oci://ghcr.io/opsdevcode/charts/repave`

4. After the assignment is signed: invoice, then `issue_repave_license.py`, then
   Package settings → **Reader** for the buyer’s GitHub org or machine user.

## Helm (your cluster)

Create `repave-license` with key `license.json` before enabling service mode.
See [install.md](install.md) and `deploy/k8s/chart/README.md`.
