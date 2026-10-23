-- Apply after T-CT-05. This service extension does not weaken public constraints.
CREATE SCHEMA knowledge;
-- Preserve ontology-only attributes (decision/covers, rule links, nested extraction/time)
-- alongside the constrained public rows, in the same transaction.
CREATE TABLE knowledge.record_extension (
    section text NOT NULL,
    id text NOT NULL,
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object' AND payload ->> 'id' = id),
    PRIMARY KEY(section, id)
);
-- Public premium_observation requires conditions. Observations without those conditions
-- remain durable here and can never enter comparison. All other public price gates apply.
CREATE TABLE knowledge.raw_premium_observation
    (LIKE public.premium_observation INCLUDING ALL);
ALTER TABLE knowledge.raw_premium_observation
    DROP CONSTRAINT chk_premium_conditions_required,
    ADD CONSTRAINT chk_raw_premium_only CHECK (
        NOT comparison_eligible AND (conditions IS NULL OR conditions = '{}'::jsonb)
        AND 'conditions' = ANY(missing_dimensions)),
    ADD FOREIGN KEY (review_decision_id) REFERENCES public.review_decision(id);
CREATE TRIGGER premium_guard BEFORE INSERT ON knowledge.raw_premium_observation
    FOR EACH ROW EXECUTE FUNCTION public.premium_guard();
CREATE TABLE knowledge.candidate (
    id text PRIMARY KEY,
    members jsonb NOT NULL,
    checked_at timestamptz NOT NULL DEFAULT now()
);
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['record_extension','raw_premium_observation','candidate'] LOOP
        EXECUTE format('CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON knowledge.%I FOR EACH ROW EXECUTE FUNCTION public.forbid_mutation()', t);
        EXECUTE format('CREATE TRIGGER append_only_truncate BEFORE TRUNCATE ON knowledge.%I FOR EACH STATEMENT EXECUTE FUNCTION public.forbid_mutation()', t);
        EXECUTE format('CREATE TRIGGER chk_no_private_ids BEFORE INSERT OR UPDATE ON knowledge.%I FOR EACH ROW EXECUTE FUNCTION public.chk_no_private_ids()', t);
    END LOOP;
END $$;
GRANT USAGE ON SCHEMA knowledge TO data_writer, knowledge_writer;
GRANT SELECT ON ALL TABLES IN SCHEMA knowledge TO data_writer;
GRANT INSERT ON knowledge.record_extension, knowledge.raw_premium_observation TO data_writer;
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA knowledge TO knowledge_writer;
-- The review_decision table keeps the existing ai-review credential boundary.
