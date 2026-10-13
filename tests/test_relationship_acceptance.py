from final_acceptance import relationship_evidence

SCRIPT = '''### SEGMENT 2 — Lead
ALEX: Rufus has already found the expenses form.
JAMIE: He calls that independent research.
RUFUS: The independence is why nobody reimburses it.
### SEGMENT 3 — Second
JAMIE: You sound almost enthusiastic.
RUFUS: I shall have to invoice for the damage to my reputation.
JAMIE: We'll pay you in exposure. To sunlight.
### SEGMENT 4 — Third
RUFUS: I prefer the view from the boardroom.
JAMIE: Because the windows don't open?
RUFUS: Because the coffee doesn't require a parachute.
'''


def exchanges():
    return [dict(segment=s, pass_=True, line_numbers=refs,
                 relationship_move='Colleague challenges Rufus; he returns the jab.',
                 comic_mechanism='Affectionate reversal', **{'pass': True})
            for s, refs in [(2,[2,3,4]),(3,[6,7,8]),(4,[10,11,12])]]


def test_one_exchange_cannot_certify_all_three_stories():
    verified, failures = relationship_evidence(SCRIPT, exchanges()[:1])
    assert len(verified) == 1
    assert any('segment 3' in f for f in failures)
    assert any('segment 4' in f for f in failures)
    assert not relationship_evidence(SCRIPT, exchanges())[1]


def test_cherry_picked_lines_and_missing_alex_are_rejected():
    rows = exchanges()
    rows[0]['line_numbers'] = [2,4,6]
    _, failures = relationship_evidence(SCRIPT, rows)
    assert any('segment 2' in f for f in failures)
    assert any('Alex' in f for f in failures)


def test_published_early_signoff_is_removed_before_canonical_close():
    import writer_room_v3_1 as writer
    from test_production_contract import SCRIPT as episode, STORIES, BOARD
    bad = episode + "\nALEX: For The AI Edge, I'm Alex. Thanks for listening."
    fixed = writer._ensure_connection_elements(bad, STORIES, BOARD, '2026-10-12')
    assert "For The AI Edge, I'm Alex. Thanks for listening." not in fixed
    assert fixed == writer._ensure_connection_elements(fixed, STORIES, BOARD, '2026-10-12')
