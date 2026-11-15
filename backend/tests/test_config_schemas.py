"""Tests for crawl-config recipe validation at the Pydantic boundary.

``CrawlConfigCreate``/``CrawlConfigUpdate`` are the schemas the API hands
around; these tests lock in the recipe constraints (profile enum,
bounded name, non-negative delay, min concurrency) and the
``mode_dump(exclude_unset=True)`` partial-update contract that
``CrawlConfigService.update`` relies on.
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models.enums import ScraperProfile
from app.schemas.crawl_config import (
    CrawlConfigCreate,
    CrawlConfigUpdate,
)


class TestCrawlConfigCreateDefaults:
    def test_minimal_payload_takes_safe_defaults(self) -> None:
        config = CrawlConfigCreate(name="books")
        assert config.scraper_profile is ScraperProfile.FETCHER
        assert config.fetch_options is None
        assert config.extraction_spec == {}
        assert config.use_proxy is False
        assert config.rotate_user_agent is True
        assert config.custom_headers is None
        assert config.custom_delay is None
        assert config.max_concurrent is None
        assert config.is_active is True
        assert config.spider_entrypoint is None

    def test_full_recipe_round_trips(self) -> None:
        fetch_options = {"timeout": 30, "proxy_retries": 3}
        config = CrawlConfigCreate(
            name="products",
            scraper_profile=ScraperProfile.SPIDER,
            fetch_options=fetch_options,
            extraction_spec={"fields": {
                "title": {"selector": "h1.title::text", "type": "css"},
            }},
            use_proxy=True,
            rotate_user_agent=False,
            custom_delay=Decimal("2.5"),
            max_concurrent=4,
        )
        assert config.fetch_options == fetch_options
        # Decimal("2.5") == 2.5 at runtime; the schema stores Decimal.
        assert config.custom_delay == 2.5
        dumped = config.model_dump()
        assert dumped["extraction_spec"]["fields"]["title"]["type"] == "css"
        assert dumped["use_proxy"] is True


class TestCrawlConfigCreateValidation:
    @pytest.mark.parametrize("bad_name", ["", "x" * 101])
    def test_name_bounds_enforced(self, bad_name: str) -> None:
        with pytest.raises(ValidationError):
            CrawlConfigCreate(name=bad_name)

    def test_unknown_profile_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CrawlConfigCreate.model_validate(
                {"name": "x", "scraper_profile": "teleport"}
            )

    def test_profiles_accepted(self) -> None:
        for profile in ScraperProfile:
            config = CrawlConfigCreate(
                name=f"cfg-{profile.value}", scraper_profile=profile
            )
            assert config.scraper_profile is profile

    def test_negative_custom_delay_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CrawlConfigCreate.model_validate(
                {"name": "x", "custom_delay": "-0.1"}
            )

    def test_zero_custom_delay_allowed(self) -> None:
        config = CrawlConfigCreate(name="x", custom_delay=Decimal(0))
        assert config.custom_delay == 0

    def test_zero_max_concurrent_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CrawlConfigCreate(name="x", max_concurrent=0)

    def test_max_concurrent_one_allowed(self) -> None:
        config = CrawlConfigCreate(name="x", max_concurrent=1)
        assert config.max_concurrent == 1

    def test_name_of_whitespace_only_not_blocked_by_schema(
        self,
    ) -> None:
        # The schema enforces length only; whitespace names are a
        # service-layer concern.  Documented so the boundary is explicit.
        config = CrawlConfigCreate(name=" ")
        assert config.name == " "


class TestCrawlConfigUpdatePartial:
    def test_exclude_unset_keeps_partial_semantics(self) -> None:
        data = CrawlConfigUpdate(name="renamed", use_proxy=True)
        updates = data.model_dump(exclude_unset=True)
        assert updates == {"name": "renamed", "use_proxy": True}

    def test_untyped_fields_not_sent(self) -> None:
        data = CrawlConfigUpdate()
        assert data.model_dump(exclude_unset=True) == {}

    def test_explicit_none_is_a_set_value(self) -> None:
        data = CrawlConfigUpdate(fetch_options=None)
        assert data.model_dump(exclude_unset=True) == {"fetch_options": None}
