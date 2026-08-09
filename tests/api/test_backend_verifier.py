from scripts.verify_backend import verify_backend


def test_backend_verifier_checks_versioned_job_route() -> None:
    verify_backend()
