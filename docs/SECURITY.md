# Security

This project is a local, single-operator inspection workstation. It is not an internet-facing multi-tenant service and does not provide authentication or authorization. Deploy it only on a trusted host and bind its API to a trusted interface.

## Trust boundaries

Uploads, archives, model bundles, reports, logs, and deletion requests are untrusted inputs. Multipart requests have a total receive-level limit before framework parsing or spooling; file count is capped at the parser boundary, and each image read is independently bounded. Parser and validation copies use a dedicated disk-backed spool root rather than the 64 MiB container tmpfs. Startup fails closed unless that root has at least twice the total request limit plus one maximum-file allowance free. Images are decoder-verified, dimension-bounded, and checked for trailing polyglot data. Archive iteration rejects links, path traversal, duplicate names, excessive file counts, and excessive expanded bytes. Model files are loaded only after manifest hash verification.

Runtime data, uploads, databases, model weights, checkpoints, official MVTec data, private predictions, and credentials remain outside Git and release images. Public UI assets are deterministic project-generated synthetic fixtures with manifest hashes.

## Error, log, and report handling

Public API errors contain a stable code, safe message, and sanitized request ID. Worker logs record identifiers and stable error types without exception text, image bytes, review notes, credentials, or filesystem roots. HTML reports escape operator-controlled text and CSV exports neutralize spreadsheet formula prefixes.

## Retention and deletion

The default upload retention is seven days and the worker performs a scheduled scan. Scheduled and explicit batch deletion resolve immutable database references for source images, anomaly maps, and overlays; prove each final path remains beneath the configured artifact root; refuse symbolic links; preserve content-addressed files still referenced by another active job; unlink only individual files; and record an idempotent audit tombstone. A tombstone immediately revokes that job's artifact routes even when a shared physical blob remains available to another job. The scheduled scan also removes aged files that have no database reference, closing storage-orphan windows after failed transactions. Blob writes hold a reentrant cross-process lock through database commit, and every physical unlink uses the same lock-to-database order; reusing a digest also refreshes its age reservation. Explicit deletion is terminal-job-only. A failed scheduled deletion is logged and retried without terminating the worker. The service never recursively deletes a configured root.

## Accepted risks

- The local profile trusts the workstation operator and host operating system.
- TLS and user authentication must be provided by a trusted reverse proxy if the service is exposed beyond localhost.
- `PASS` and `REVIEW` are model evidence, not automatic production disposition or defect classification.
- The MVTec AD 2 dataset is not redistributed; its CC BY-NC-SA 4.0 terms are separate from project source code.

Report suspected vulnerabilities privately to the repository owner before public disclosure. Do not attach proprietary images, credentials, or private evaluation outputs.
