import math
import unittest
import numpy as np

import aerocalc.core as core
from aerocalc.modules import load_all

load_all()


class TestScientificCalculator(unittest.TestCase):
    def setUp(self):
        self.calc = core.get("scientific-calculator")
        self.assertIsNotNone(self.calc)

    def test_comp_arithmetic_and_trig(self):
        compute = self.calc["compute"]
        # Basic arithmetic & operator precedence
        r = compute({"calc_mode": "comp", "comp_expr": "2 + 3 * 4 - 6 / 2", "angle_mode": "deg"})
        self.assertEqual(r.groups[0]["rows"][0]["value"], 11.0)

        # Trigonometry in degrees: sin(30) = 0.5, cos(60) = 0.5
        r = compute({"calc_mode": "comp", "comp_expr": "sin(30) + cos(60)", "angle_mode": "deg"})
        self.assertAlmostEqual(r.groups[0]["rows"][0]["value"], 1.0, places=6)

        # Trigonometry in radians: sin(pi / 2) = 1.0
        r = compute({"calc_mode": "comp", "comp_expr": "sin(pi / 2)", "angle_mode": "rad"})
        self.assertAlmostEqual(r.groups[0]["rows"][0]["value"], 1.0, places=6)

        # Powers and roots: 2^3 + sqrt(16) = 8 + 4 = 12
        r = compute({"calc_mode": "comp", "comp_expr": "2^3 + sqrt(16)", "angle_mode": "deg"})
        self.assertEqual(r.groups[0]["rows"][0]["value"], 12.0)

    def test_matrix_operations(self):
        compute = self.calc["compute"]
        # Determinant of 3x3
        r = compute({
            "calc_mode": "matrix",
            "mat_op": "det_a",
            "mat_a": "1, 2, 3\n0, 1, 4\n5, 6, 0",
            "mat_b": ""
        })
        # det = 1*(0-24) - 2*(0-20) + 3*(0-5) = -24 + 40 - 15 = 1
        det_val = r.groups[1]["rows"][0]["value"]
        self.assertAlmostEqual(det_val, 1.0, places=6)

        # Matrix inverse of 2x2: [[4, 7], [2, 6]] -> det = 24 - 14 = 10
        r = compute({
            "calc_mode": "matrix",
            "mat_op": "inv_a",
            "mat_a": "4, 7\n2, 6",
            "mat_b": ""
        })
        self.assertAlmostEqual(r.groups[1]["rows"][0]["value"], 10.0, places=6)

        # Matrix multiplication
        r = compute({
            "calc_mode": "matrix",
            "mat_op": "mult",
            "mat_a": "1, 2\n3, 4",
            "mat_b": "2, 0\n1, 2"
        })
        # [[1*2+2*1, 1*0+2*2], [3*2+4*1, 3*0+4*2]] = [[4, 4], [10, 8]]
        self.assertTrue(len(r.steps) > 0)

    def test_equation_solvers(self):
        compute = self.calc["compute"]
        # 2x2 Linear: 2x + 3y = 8, x - y = -1 -> x = 1, y = 2
        r = compute({
            "calc_mode": "eqn",
            "eqn_type": "linear_2x2",
            "a1": 2, "b1": 3, "c1": 8,
            "a2": 1, "b2": -1, "c2": -1
        })
        x_val = r.groups[0]["rows"][0]["value"]
        y_val = r.groups[0]["rows"][1]["value"]
        self.assertAlmostEqual(x_val, 1.0, places=6)
        self.assertAlmostEqual(y_val, 2.0, places=6)

        # Quadratic: x^2 - 5x + 6 = 0 -> roots 3 and 2
        r = compute({
            "calc_mode": "eqn",
            "eqn_type": "poly_quad",
            "poly_a": 1, "poly_b": -5, "poly_c": 6
        })
        r1 = r.groups[0]["rows"][3]["value"]
        r2 = r.groups[0]["rows"][4]["value"]
        roots = sorted([r1, r2])
        self.assertAlmostEqual(roots[0], 2.0, places=6)
        self.assertAlmostEqual(roots[1], 3.0, places=6)

        # Quadratic with complex roots: x^2 + 1 = 0 -> +/- 1i
        r = compute({
            "calc_mode": "eqn",
            "eqn_type": "poly_quad",
            "poly_a": 1, "poly_b": 0, "poly_c": 1
        })
        self.assertIn("i", r.groups[0]["rows"][3]["value"])

    def test_set_operations(self):
        compute = self.calc["compute"]
        r = compute({
            "calc_mode": "sets",
            "set_a": "1, 2, 3, 4, 5",
            "set_b": "3, 4, 5, 6, 7",
            "set_c": ""
        })
        # |A| = 5, |B| = 5
        self.assertEqual(r.groups[0]["rows"][0]["value"], 5)
        self.assertEqual(r.groups[0]["rows"][1]["value"], 5)
        # Check union and intersection steps exist
        self.assertTrue(len(r.steps) >= 3)

    def test_calculus_and_table(self):
        compute = self.calc["compute"]
        # Definite integral: int_0^3 x^2 dx = [x^3/3]_0^3 = 9.0
        r = compute({
            "calc_mode": "table",
            "calc_submode": "integral",
            "calc_func": "x**2",
            "int_a": 0, "int_b": 3
        })
        val = r.groups[0]["rows"][0]["value"]
        self.assertAlmostEqual(val, 9.0, places=5)

        # Numerical derivative: d/dx(x^3) at x = 2 -> 3*2^2 = 12.0
        r = compute({
            "calc_mode": "table",
            "calc_submode": "deriv",
            "calc_func": "x**3",
            "x_eval": 2.0
        })
        d_val = r.groups[0]["rows"][0]["value"]
        self.assertAlmostEqual(d_val, 12.0, places=4)

    def test_base_n_conversions(self):
        compute = self.calc["compute"]
        r = compute({
            "calc_mode": "base_n",
            "base_num": 255,
            "base_num_b": 15
        })
        hex_val = r.groups[0]["rows"][1]["value"]
        self.assertEqual(hex_val, "0xFF")
        # gcd(255, 15) = 15
        gcd_val = r.groups[2]["rows"][0]["value"]
        self.assertEqual(gcd_val, 15)


if __name__ == "__main__":
    unittest.main()

