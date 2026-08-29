from unittest.mock import Mock
from uuid import uuid4

import pytest
from stock_platform.application.learning.approval import record_lesson_decision
from stock_platform.application.learning.promotion import HumanActor, PolicyPromotionForbidden


@pytest.mark.parametrize(
    "actor",
    [
        HumanActor("anonymous", authenticated=False),
        HumanActor("automation-42", authenticated=True, is_human=False),
        HumanActor("weekly-agent", authenticated=True),
    ],
)
def test_lesson_decision_rejects_non_human_actors_before_database_access(
    actor: HumanActor,
) -> None:
    connection = Mock()

    with pytest.raises(PolicyPromotionForbidden, match="authenticated human approval required"):
        record_lesson_decision(
            connection,
            review_id=uuid4(),
            lesson_id=uuid4(),
            actor=actor,
            action="APPROVE",
            rationale="must be human-reviewed",
        )

    connection.execute.assert_not_called()
