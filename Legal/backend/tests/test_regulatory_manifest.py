"""Unit tests for the regulatory corpus manifest loader."""

from __future__ import annotations

import pytest

from app.services.regulatory_manifest import (
    DOMAINS,
    ManifestRow,
    all_official_hosts,
    issuer_domains,
    load_manifest,
    manifest_row,
    official_host,
    require_row,
    reload_manifest,
    rows_by_priority,
    ManifestError,
)


def test_shipped_manifest_loads_every_row() -> None:
    rows = reload_manifest()
    assert len(rows) == 30
    assert all(r.doc_id for r in rows.values())
    assert all(r.domain in DOMAINS for r in rows.values())


def test_dated_row_resolves_effective_date() -> None:
    row = require_row("LEND-DLD-2025")
    assert row.effective_date is not None
    assert row.effective_date.isoformat() == "2025-05-08"
    assert row.is_living is False
    assert row.supersedes == ["2022 Digital Lending Guidelines", "2023 DLG Guidelines"]
    assert "cooling-off" in row.tags


def test_check_latest_row_has_no_effective_date() -> None:
    row = require_row("AML-MD-KYC")
    assert row.is_living is True
    assert row.effective_date is None


def test_download_mode_drives_auto_fetch() -> None:
    assert require_row("LEND-DLD-2025").can_auto_fetch is True
    # Bare Acts are hand-downloaded from India Code.
    assert require_row("DP-DPDPA-2023").can_auto_fetch is False


def test_unknown_doc_id_is_rejected() -> None:
    assert manifest_row("NOPE-123") is None
    with pytest.raises(ManifestError):
        require_row("NOPE-123")


def test_priority_filter() -> None:
    p1 = rows_by_priority("P1")
    assert len(p1) == 12
    assert all(r.priority == "P1" for r in p1)


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.rbi.org.in/scripts/NotificationUser.aspx?Id=12848", "rbi.org.in"),
        # A human hint rather than a deep link must not become a hostname.
        ("https://www.indiacode.nic.in (search: PMLA 2002)", "indiacode.nic.in"),
        ("https://irdai.gov.in/consolidated-gazette", "irdai.gov.in"),
        ("", None),
        (None, None),
        ("not a url", None),
    ],
)
def test_official_host_extraction(url: str | None, expected: str | None) -> None:
    assert official_host(url) == expected


def test_issuer_domains_are_real_hosts() -> None:
    hosts = all_official_hosts()
    assert "rbi.org.in" in hosts
    assert "sebi.gov.in" in hosts
    assert all(" " not in h and "(" not in h for h in hosts)

    per_domain = issuer_domains()
    assert "npci.org.in" in per_domain["payments_banking"]
    assert "meity.gov.in" in per_domain["data_privacy_cyber"]


def test_row_parses_semicolon_lists_and_blank_urls() -> None:
    row = ManifestRow(
        doc_id="X",
        domain="aml_kyc",
        title="T",
        issuer="RBI",
        doc_type="circular",
        supersedes="A; B ;",
        tags="one;two",
        direct_pdf_url="  ",
    )
    assert row.supersedes == ["A", "B"]
    assert row.tags == ["one", "two"]
    assert row.direct_pdf_url is None


def test_load_manifest_is_cached() -> None:
    assert load_manifest() is load_manifest()
