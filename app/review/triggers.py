from alembic_utils.pg_function import PGFunction
from alembic_utils.pg_trigger import PGTrigger

# constraint to make the agent's proposal never overwritten
refuse_proposal_update = PGFunction(
    schema="public",
    signature="proposals_refuse_update()",
    definition="""RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'proposals are append-only; store a new proposal instead'
        USING ERRCODE = 'check_violation';
END;
$$""",
)

proposals_append_only_trigger = PGTrigger(
    schema="public",
    signature="proposals_append_only",
    on_entity="public.proposals",
    definition="""BEFORE UPDATE ON public.proposals
    FOR EACH ROW EXECUTE FUNCTION public.proposals_refuse_update()""",
)

# registered in migrations/env.py
ENTITIES = [
    refuse_proposal_update,
    proposals_append_only_trigger,
]
