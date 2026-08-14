from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType

from agent_experience import DeterministicMiner, build_baseline_profile, definition_from_delta


def load_demo() -> ModuleType:
    path = Path(__file__).parents[1] / "examples" / "deepseek_experience_demo.py"
    spec = importlib.util.spec_from_file_location("deepseek_experience_demo", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TransparentDemoTests(unittest.TestCase):
    def test_score_explains_success_and_failure(self) -> None:
        demo = load_demo()
        complete = "\n".join(
            f"第{day}天 交通火车；住宿酒店；餐饮午餐晚餐；预算人民币1000元；"
            "按实际日期复核官网。" + "详细活动与路线安排。" * 50
            for day in range(1, 6)
        )
        success = demo.score_plan(complete, 5)
        failure = demo.score_plan("简短建议", 5)
        self.assertTrue(success.passed)
        self.assertFalse(failure.passed)
        self.assertGreater(success.total, failure.total)

    def test_demo_maps_domain_scores_to_generic_features(self) -> None:
        demo = load_demo()
        text = "\n".join(
            f"第{day}天 交通；住宿；餐饮；预算人民币；按实际日期复核。" + "安排" * 200
            for day in range(1, 6)
        )
        call = demo.ModelCall(text, 100, 200, 300, 1.0, "model", "stop")
        score = demo.score_plan(text, 5)
        first = demo.score_features("run-a", score, call)
        second = demo.score_features("run-b", score, call)
        mined = DeterministicMiner().mine(build_baseline_profile("demo", "1"), (first, second))
        definition = definition_from_delta(mined, task_type="travel_plan")
        selection = demo.select_rules(definition, "task")
        self.assertFalse(mined.used_llm)
        self.assertEqual(mined.mining_input_tokens, 0)
        self.assertTrue(selection.selected)
        self.assertIn("【AgentExperience 选择结果】", demo.experience_prompt("task", selection))


if __name__ == "__main__":
    unittest.main()
