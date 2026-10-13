import writer_room_v3_1 as writer


def test_each_scene_gets_its_own_character_plan_and_legacy_index_works():
    first = {'story_index': 1, 'source_url': 'https://example.com/one', 'cast_direction': {'alex': 'Explore the first result'}}
    second = {'source_index': 2, 'source_url': 'https://example.com/two', 'cast_direction': {'jamie': 'Understand the second result'}}
    board = {'story_scenes': [first, second]}
    assert writer._scene_plan(board, 2, {'url': first['source_url']}) == first
    assert writer._scene_plan(board, 3, {'url': second['source_url']}) == second
    assert writer._scene_plan(board, 4, {'url': second['source_url']}) == {}
    assert writer._scene_plan(board, 2, {'url': second['source_url']}) == {}


def test_missing_or_malformed_scene_plan_does_not_invent_one():
    for scenes in [None, {}, ['bad'], [{'story_index': 3}]]:
        assert writer._scene_plan({'story_scenes': scenes}, 2, {}) == {}
