from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.constants import BUSINESS_TAG_DISPLAY_MAP
from app.rebuild_engine import (
    enrich_entries_with_linked_sources,
    find_linked_matches,
    find_previous_match,
    has_meaningful_delta,
)
from app.services import build_frontend_render_model
from app.utils import normalize_compare_text


def make_entry(
    *,
    contract_version: str = "v2",
    module_key: str = "themed_tracks",
    module_id: int = 6,
    subsection_path: str = "6.1",
    section_type: str = "新增",
    title: str = "Space fragrance launch",
    time_text: str = "2026-04-11",
    event_date: str = "2026-04-11",
    source_name: str = "Brand Site",
    source_level: str = "A2",
    source_url: str = "",
    core_content: str = "Brand published a new space fragrance launch update.",
    why_included: str = "Useful for track monitoring.",
    delta_text: str = "",
    business_tags=None,
    event_anchor: str = "",
    canonical_title: str = "",
) -> dict:
    evidence = {
        "contract_version": contract_version,
        "delta_text": delta_text,
        "business_tags": list(business_tags or []),
        "normalization_notes": [],
    }
    if event_anchor:
        evidence["event_anchor"] = event_anchor
    if canonical_title:
        evidence["canonical_title"] = canonical_title
    return {
        "id": 1,
        "report_date": "2026-04-12",
        "module_id": module_id,
        "module_key": module_key,
        "subsection_path": subsection_path,
        "section_type": section_type,
        "entry_type": "real",
        "event_key": f"{module_key}:test",
        "title": title,
        "time_text": time_text,
        "event_date": event_date,
        "source_name": source_name,
        "source_title": title,
        "source_url": source_url,
        "core_content": core_content,
        "why_included": why_included,
        "supporting_sources_json": [],
        "display_status": "新增",
        "source_level": source_level,
        "needs_review": 0,
        "is_deleted": 0,
        "evidence_json": evidence,
    }


def assert_anchor_and_exact_first_matching() -> None:
    anchor_previous = make_entry(
        title="Earlier wording",
        source_name="Media",
        event_anchor="anchor-space-launch",
    )
    exact_previous = make_entry(
        title="Space fragrance launch",
        source_name="Brand Site",
    )
    current_anchor = make_entry(
        title="Totally rewritten wording",
        source_name="Another Source",
        event_anchor="anchor-space-launch",
    )
    matched = find_previous_match([exact_previous, anchor_previous], current_anchor)
    assert matched is not None and matched["title"] == "Earlier wording"

    canonical_previous = make_entry(
        title="Historic title",
        canonical_title="brand_space_launch",
        source_name="Archive",
    )
    current_canonical = make_entry(
        title="Current rewritten title",
        canonical_title="brand_space_launch",
        source_name="Brand Site",
    )
    matched = find_previous_match([exact_previous, canonical_previous], current_canonical)
    assert matched is not None and matched["title"] == "Historic title"

    fuzzy_like_previous = make_entry(title="Space fragrance launch expanded")
    current_v2 = make_entry(title="Space fragrance launch")
    assert find_previous_match([fuzzy_like_previous], current_v2) is None


def assert_delta_first_rules() -> None:
    previous_v2 = make_entry(contract_version="v2", delta_text="", why_included="Old explanation")
    same_fact_rewritten_why = make_entry(
        contract_version="v2",
        delta_text="",
        why_included="A completely rewritten explanation should not count as an update.",
    )
    assert not has_meaningful_delta(previous_v2, same_fact_rewritten_why)

    source_url_gain = make_entry(contract_version="v2", delta_text="", source_url="https://example.com/new")
    assert has_meaningful_delta(previous_v2, source_url_gain)

    new_time_node = make_entry(
        contract_version="v2",
        delta_text="",
        time_text="2026-04-11; 2026-04-13",
        event_date="2026-04-11",
    )
    assert has_meaningful_delta(previous_v2, new_time_node)


def assert_v1_fallback_keeps_working_but_shrinks_why_weight() -> None:
    previous_v1 = make_entry(
        contract_version="v1",
        delta_text="",
        core_content="Brand published a launch note.",
        why_included="Initial observation.",
    )
    why_only_rewrite = make_entry(
        contract_version="v1",
        delta_text="",
        core_content="Brand published a launch note.",
        why_included="This is a much longer rewritten explanation, but the fact itself did not change.",
    )
    assert not has_meaningful_delta(previous_v1, why_only_rewrite)

    core_changed = make_entry(
        contract_version="v1",
        delta_text="",
        core_content="Brand confirmed a new overseas channel launch and order conversion signal.",
        why_included="Observation moved to channel conversion evidence.",
    )
    assert has_meaningful_delta(previous_v1, core_changed)


def assert_business_tags_drive_grouping_first() -> None:
    tagged_render_model = {
        "groups": [
            {
                "title": "6.1 This title does not contain fallback keywords",
                "category": "Generic bucket",
                "blocks": [
                    {
                        "type": "card",
                        "card": {
                            "title": "A neutral title",
                            "status": "新增",
                            "needs_review": False,
                            "compare_meta": {"business_tags": ["space_home_fragrance"]},
                        },
                    }
                ],
            }
        ],
        "status_counts": {"新增": 1},
    }
    tagged_frontend = build_frontend_render_model("themed_tracks", tagged_render_model, "新增")
    assert tagged_frontend["groups"][0]["display_category"] == BUSINESS_TAG_DISPLAY_MAP["space_home_fragrance"]

    fallback_render_model = {
        "groups": [
            {
                "title": "6.1 空间香氛新品观察",
                "category": "空间香氛新品观察",
                "blocks": [
                    {
                        "type": "card",
                        "card": {
                            "title": "空间香氛新品观察",
                            "status": "新增",
                            "needs_review": False,
                            "compare_meta": {},
                        },
                    }
                ],
            }
        ],
        "status_counts": {"新增": 1},
    }
    fallback_frontend = build_frontend_render_model("themed_tracks", fallback_render_model, "新增")
    assert fallback_frontend["groups"][0]["display_category"] == BUSINESS_TAG_DISPLAY_MAP["space_home_fragrance"]


def assert_safe_link_is_exact_first_and_conservative() -> None:
    exact_title = normalize_compare_text("Space fragrance launch")
    grouped_registry = {
        exact_title: [
            {
                "title": "Space fragrance launch",
                "source_name": "Brand Site",
                "source_url": "https://example.com/exact",
                "time_text": "2026-04-11",
                "source_level": "A2",
            },
            {
                "title": "Space fragrance launch",
                "source_name": "Brand Site",
                "source_url": "https://example.com/older",
                "time_text": "2026-04-08",
                "source_level": "A2",
            },
            {
                "title": "Space fragrance launch",
                "source_name": "Media",
                "source_url": "https://example.com/media",
                "time_text": "2026-04-11",
                "source_level": "C",
            },
        ]
    }
    item = make_entry(title="Space fragrance launch", source_name="Brand Site", source_url="")
    matches = find_linked_matches(item, grouped_registry)
    assert len(matches) == 1
    assert matches[0]["source_url"] == "https://example.com/exact"

    ambiguous_registry_rows = [
        {
            "title": "Space fragrance launch",
            "source_name": "Brand Site",
            "source_url": "https://example.com/a",
            "time_text": "2026-04-11",
            "source_level": "A2",
            "path": "linked-a.docx",
        },
        {
            "title": "Space fragrance launch",
            "source_name": "Brand Site",
            "source_url": "https://example.com/b",
            "time_text": "2026-04-11",
            "source_level": "A2",
            "path": "linked-b.docx",
        },
    ]
    ambiguous_entry = make_entry(title="Space fragrance launch", source_name="Brand Site", source_url="")
    enrich_entries_with_linked_sources([ambiguous_entry], ambiguous_registry_rows)
    assert ambiguous_entry["source_url"] == ""
    assert ambiguous_entry["evidence_json"]["link_backfill_mode"] == "skipped_ambiguous"
    assert ambiguous_entry["evidence_json"]["match_mode"] == "ambiguous_title_date_source_exact"

    preserved_entry = make_entry(
        title="Space fragrance launch",
        source_name="Brand Site",
        source_url="https://example.com/original",
    )
    enrich_entries_with_linked_sources([preserved_entry], ambiguous_registry_rows)
    assert preserved_entry["source_url"] == "https://example.com/original"
    assert preserved_entry["evidence_json"]["link_backfill_mode"] == "preserved_existing_source_url"
    assert preserved_entry["evidence_json"]["match_mode"] == "existing_source_url"


def main() -> None:
    assert_anchor_and_exact_first_matching()
    assert_delta_first_rules()
    assert_v1_fallback_keeps_working_but_shrinks_why_weight()
    assert_business_tags_drive_grouping_first()
    assert_safe_link_is_exact_first_and_conservative()
    print("rebuild_engine_stability_test_ok")


if __name__ == "__main__":
    main()
