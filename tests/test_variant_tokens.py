from deal_finder.variant_tokens import build_variant_token_map, filter_candidates, group_families


def test_variant_map_uses_only_distinguishing_tokens_within_a_family():
    names = ["PS5 Slim", "PS5 Slim Digital", "Nintendo Switch OLED"]

    token_map = build_variant_token_map(names)

    assert token_map["PS5 Slim"] == set()
    assert token_map["PS5 Slim Digital"] == {"digital"}
    assert token_map["Nintendo Switch OLED"] == set()
    assert ["PS5 Slim", "PS5 Slim Digital"] in group_families(names)


def test_base_and_qualified_variants_cannot_cross_match():
    names = ["PS5 Slim", "PS5 Slim Digital"]
    token_map = build_variant_token_map(names)

    assert filter_candidates("PS5 Slim console", "PS5 Slim", token_map, names)
    assert not filter_candidates("PS5 Slim Digital console", "PS5 Slim", token_map, names)
    assert filter_candidates("PS5 Slim Digital console", "PS5 Slim Digital", token_map, names)
    assert not filter_candidates("PS5 Slim console", "PS5 Slim Digital", token_map, names)
