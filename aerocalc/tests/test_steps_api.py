import sys
import unittest

sys.path.insert(0, '.')
from app import app


class TestStepsAPI(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_calcs_have_steps(self):
        from aerocalc import core
        calcs = [c['id'] for c in core.all_calculators()]
        self.assertEqual(len(calcs), 58)
        for c in calcs:
            with self.subTest(calc=c):
                res = self.client.post(f'/api/compute/{c}', json={})
                self.assertEqual(res.status_code, 200)
                data = res.get_json()
                self.assertIn('steps', data)
                steps = data['steps']
                self.assertGreater(len(steps), 0, f"No steps found for {c}")
                for s in steps:
                    self.assertIn('title', s)
                    self.assertIn('formula', s)
                    self.assertIn('substitution', s)
                    self.assertIn('result', s)
                    self.assertIn('explanation', s)
                    self.assertTrue(len(s['title']) > 0)
                    self.assertTrue(len(s['formula']) > 0)
                    self.assertTrue(len(s['explanation']) > 0)


if __name__ == '__main__':
    unittest.main()

