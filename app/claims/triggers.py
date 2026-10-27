from alembic_utils.pg_function import PGFunction
from alembic_utils.pg_trigger import PGTrigger

# enforces the claim status changes against the `claim_status_transitions` table
enforce_status_transition = PGFunction(
    schema="public",
    signature="claims_enforce_status_transition()",
    definition="""RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'pending_upload' THEN
            RAISE EXCEPTION 'a new claim must start in pending_upload, not %', NEW.status
                USING ERRCODE = 'check_violation';
        END IF;
    ELSIF NEW.status IS DISTINCT FROM OLD.status AND NOT EXISTS (
        SELECT 1 FROM claim_status_transitions
        WHERE from_status = OLD.status AND to_status = NEW.status
    ) THEN
        RAISE EXCEPTION 'claim status cannot change from % to %', OLD.status, NEW.status
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$""",
)

status_transition_trigger = PGTrigger(
    schema="public",
    signature="claims_status_transition",
    on_entity="public.claims",
    definition="""BEFORE INSERT OR UPDATE OF status ON public.claims
    FOR EACH ROW EXECUTE FUNCTION public.claims_enforce_status_transition()""",
)

# registered in migrations/env.py
ENTITIES = [
    enforce_status_transition,
    status_transition_trigger,
]
