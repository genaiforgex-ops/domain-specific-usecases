"""Tests for MSA prompt revision edit memory."""

import unittest
from unittest.mock import MagicMock


class MsaPromptRevisionServiceTests(unittest.TestCase):
    def test_operation_to_dict(self) -> None:
        try:
            from app.services.ai_service import DocxOperationItem
            from app.services.msa_prompt_revision_service import operation_to_dict
        except Exception:
            self.skipTest("app dependencies not installed")

        op = DocxOperationItem(
            op_type="replace_span",
            anchor_id="body:p:0",
            after_anchor_id=None,
            target_text="old",
            content="new",
            description="test",
            confidence=0.9,
        )
        d = operation_to_dict(op)
        self.assertEqual(d["op_type"], "replace_span")
        self.assertEqual(d["anchor_id"], "body:p:0")

    def test_get_edit_memory_empty(self) -> None:
        try:
            from app.services.msa_prompt_revision_service import get_edit_memory
        except Exception:
            self.skipTest("app dependencies not installed")

        db = MagicMock()
        db.execute.return_value.scalars.return_value.all.return_value = []
        memory = get_edit_memory(db, tracker_id=1)
        self.assertEqual(memory, [])

    def test_multi_turn_memory_order(self) -> None:
        try:
            from app.services.msa_prompt_revision_service import get_edit_memory
        except Exception:
            self.skipTest("app dependencies not installed")

        rev1 = MagicMock()
        rev1.change_summary = "First edit: capped liability"
        rev1.instruction = "cap liability"
        rev2 = MagicMock()
        rev2.change_summary = "Second edit: added DPDP"
        rev2.instruction = "add dpdp"
        db = MagicMock()
        db.execute.return_value.scalars.return_value.all.return_value = [rev2, rev1]
        memory = get_edit_memory(db, tracker_id=1, limit=5)
        self.assertEqual(len(memory), 2)
        self.assertEqual(memory[0], "First edit: capped liability")
        self.assertEqual(memory[1], "Second edit: added DPDP")


if __name__ == "__main__":
    unittest.main()
