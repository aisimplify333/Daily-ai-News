import json
import unittest
from unittest.mock import patch
import writer_room_v3_1 as writer
from crew_review import review_final_scenes


class RufusDispatchTests(unittest.TestCase):
    def test_planned_dispatch_reaches_writer_and_final_reviewer(self):
        desk = {'market_or_region': 'Hong Kong', 'capital_policy_or_infrastructure_move': 'SOURCE_SPECIFIC_CAPITAL_MOVE'}
        board = {'rufus_global_markets_desk': desk}
        prompt = writer._writer_prompt([{'headline':'AI financing'}], [], '2026-10-07', board, {})
        self.assertIn('SOURCE_SPECIFIC_CAPITAL_MOVE', prompt)
        self.assertIn('Hong Kong', prompt)
        seen = []
        def request(prompt):
            seen.append(prompt)
            return json.dumps({'edits':[]})
        result, _ = review_final_scenes('ALEX: Hello.', [], board, request, lambda s:s, lambda s:{})
        self.assertIn('SOURCE_SPECIFIC_CAPITAL_MOVE', seen[0])
        self.assertEqual(result, 'ALEX: Hello.')

    def test_dispatch_history_is_explicitly_planned_not_eyewitness_evidence(self):
        episodes = [{'date':'2026-10-06', 'planned_rufus_dispatch':{'market_or_region':'London'}}]
        fuel = writer._continuity_fuel(episodes, {})
        self.assertEqual(fuel['recent_editorial_patterns'][0]['planned_rufus_dispatch']['market_or_region'], 'London')


if __name__ == '__main__':
    unittest.main()
