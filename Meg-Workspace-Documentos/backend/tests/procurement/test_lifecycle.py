from app.engines.procurement.lifecycle import TenderLifecycle, InvalidTenderTransition


def test_happy_path_transitions_are_closed():
    state = "DISCOVERED"
    for target in (
        "INGESTED", "JURISDICTIONED", "REQUIREMENTS_MAPPED", "BIDDER_READY",
        "TECHNICAL_MODEL_READY", "QUANTIFIED", "ECONOMIC_MODEL_READY",
        "SCHEDULE_READY", "DOCUMENTS_READY", "CROSS_VALIDATED", "QA_READY",
        "HUMAN_APPROVAL", "SIGNED", "SUBMISSION_READY", "SUBMITTED", "ARCHIVED",
    ):
        TenderLifecycle.assert_transition(state, target)
        state = target


def test_illegal_jump_is_rejected():
    try:
        TenderLifecycle.assert_transition("DISCOVERED", "SUBMITTED")
    except InvalidTenderTransition:
        return
    raise AssertionError("The state machine accepted an illegal jump")
