/* ════════════════════════════════════════════════════════════════════════
   sp_run_data_quality  +  sp_load_dq_rule
   --------------------------------------------------------------------------
   Configurable validation framework. Rules live in GOVERNANCE.DQ_RULE_CATALOG
   (synced from config/data_quality_rules.yaml). For a given entity, the
   engine evaluates every active rule against PENDING STAGING records using
   dynamic SQL, writes one row per (record, rule) to GOVERNANCE.DQ_RESULT,
   updates each record's dq_status, quarantines ERROR-severity failures, and
   asks Cortex for a plain-English explanation of a sampled set of failures.

   DELIVERABLE: "Validation Framework"
   ════════════════════════════════════════════════════════════════════════ */

USE DATABASE INSURANCE_PLATFORM;
USE SCHEMA GOVERNANCE;

-- ── Upsert a single rule (called by scripts/sync_dq_rules.py) ───────────
CREATE OR REPLACE PROCEDURE SP_LOAD_DQ_RULE(
    RULE_ID STRING, ENTITY STRING, DESCRIPTION STRING, SEVERITY STRING,
    RULE_TYPE STRING, EXPRESSION STRING, EXPLAIN BOOLEAN
)
RETURNS STRING
LANGUAGE SQL
AS
$$
BEGIN
    MERGE INTO GOVERNANCE.DQ_RULE_CATALOG t
    USING (SELECT :RULE_ID AS rid) s ON t.rule_id = s.rid
    WHEN MATCHED THEN UPDATE SET
        entity = :ENTITY, description = :DESCRIPTION, severity = :SEVERITY,
        rule_type = :RULE_TYPE, expression = :EXPRESSION, explain = :EXPLAIN,
        updated_at = CURRENT_TIMESTAMP()
    WHEN NOT MATCHED THEN INSERT
        (rule_id, entity, description, severity, rule_type, expression, explain)
        VALUES (:RULE_ID, :ENTITY, :DESCRIPTION, :SEVERITY, :RULE_TYPE, :EXPRESSION, :EXPLAIN);
    RETURN 'Loaded rule ' || :RULE_ID;
END;
$$;

-- ── Run all active rules for an entity against PENDING records ──────────
CREATE OR REPLACE PROCEDURE SP_RUN_DATA_QUALITY(ENTITY STRING, MODEL STRING)
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    batch_id  STRING  DEFAULT UUID_STRING();
    tbl       STRING  DEFAULT IFF(:ENTITY = 'claim', 'STAGING.STG_CLAIM', 'STAGING.STG_POLICY');
    n_records INTEGER DEFAULT 0;
    n_rules   INTEGER DEFAULT 0;
    n_error   INTEGER DEFAULT 0;
    n_warn    INTEGER DEFAULT 0;
    n_quar    INTEGER DEFAULT 0;
BEGIN
    INSERT INTO GOVERNANCE.DQ_BATCH_LOG (batch_id, entity, started_at, status)
    VALUES (:batch_id, :ENTITY, CURRENT_TIMESTAMP(), 'RUNNING');

    -- Evaluate each rule with one dynamic INSERT … SELECT over the staging table.
    FOR r IN (
        SELECT rule_id, severity, expression
        FROM GOVERNANCE.DQ_RULE_CATALOG
        WHERE active = TRUE AND entity = :ENTITY AND rule_type = 'expression'
    ) DO
        n_rules := n_rules + 1;
        LET sql STRING :=
            'INSERT INTO GOVERNANCE.DQ_RESULT ' ||
            '(batch_id, entity, stg_id, broker_code, rule_id, severity, passed) ' ||
            'SELECT ''' || :batch_id || ''', ''' || :ENTITY || ''', stg_id, broker_code, ''' ||
            r.rule_id || ''', ''' || r.severity || ''', ' ||
            'IFF(' || r.expression || ', TRUE, FALSE) ' ||
            'FROM ' || :tbl || ' WHERE dq_status = ''PENDING''';
        EXECUTE IMMEDIATE :sql;
    END FOR;

    -- Roll up per-record status from this batch's results.
    LET upd STRING :=
        'UPDATE ' || :tbl || ' s SET dq_status = agg.new_status ' ||
        'FROM (SELECT stg_id, ' ||
        '        CASE WHEN MIN(IFF(passed, 1, IFF(severity=''ERROR'',-1,0))) = -1 THEN ''FAIL'' ' ||
        '             WHEN MIN(IFF(passed, 1, 0)) = 0 THEN ''WARN'' ELSE ''PASS'' END AS new_status ' ||
        '      FROM GOVERNANCE.DQ_RESULT WHERE batch_id = ''' || :batch_id || ''' ' ||
        '      GROUP BY stg_id) agg ' ||
        'WHERE s.stg_id = agg.stg_id';
    EXECUTE IMMEDIATE :upd;

    -- Quarantine ERROR failures.
    LET quar STRING :=
        'INSERT INTO STAGING.STG_QUARANTINE (entity, stg_id, broker_code, failed_rules, record_snapshot) ' ||
        'SELECT ''' || :ENTITY || ''', s.stg_id, s.broker_code, ' ||
        '       ARRAY_AGG(d.rule_id), ANY_VALUE(OBJECT_CONSTRUCT(*)) ' ||
        'FROM ' || :tbl || ' s JOIN GOVERNANCE.DQ_RESULT d ON s.stg_id = d.stg_id ' ||
        'WHERE d.batch_id = ''' || :batch_id || ''' AND d.passed = FALSE AND d.severity = ''ERROR'' ' ||
        'GROUP BY s.stg_id, s.broker_code';
    EXECUTE IMMEDIATE :quar;
    n_quar := SQLROWCOUNT;

    -- Cortex: explain a sample of failures in plain English (cost-bounded).
    LET explain_sql STRING :=
        'UPDATE GOVERNANCE.DQ_RESULT d ' ||
        'SET cortex_explanation = SEMANTIC.FN_EXPLAIN_FAILURE(''' || :MODEL || ''', ''' || :ENTITY || ''', ' ||
        '    cat.description, TO_VARCHAR(OBJECT_CONSTRUCT(*))) ' ||
        'FROM GOVERNANCE.DQ_RULE_CATALOG cat, ' || :tbl || ' s ' ||
        'WHERE d.rule_id = cat.rule_id AND d.stg_id = s.stg_id ' ||
        '  AND d.batch_id = ''' || :batch_id || ''' AND d.passed = FALSE AND cat.explain = TRUE ' ||
        '  AND d.result_id IN (SELECT result_id FROM GOVERNANCE.DQ_RESULT ' ||
        '       WHERE batch_id = ''' || :batch_id || ''' AND passed = FALSE LIMIT 50)';
    EXECUTE IMMEDIATE :explain_sql;

    -- Metrics
    SELECT COUNT(DISTINCT stg_id) INTO n_records FROM GOVERNANCE.DQ_RESULT WHERE batch_id = :batch_id;
    SELECT COUNT(*) INTO n_error FROM GOVERNANCE.DQ_RESULT WHERE batch_id = :batch_id AND passed = FALSE AND severity = 'ERROR';
    SELECT COUNT(*) INTO n_warn  FROM GOVERNANCE.DQ_RESULT WHERE batch_id = :batch_id AND passed = FALSE AND severity = 'WARN';

    UPDATE GOVERNANCE.DQ_BATCH_LOG
       SET records_evaluated = :n_records, rules_evaluated = :n_rules,
           error_failures = :n_error, warn_failures = :n_warn, quarantined = :n_quar,
           finished_at = CURRENT_TIMESTAMP(), status = 'SUCCESS'
     WHERE batch_id = :batch_id;

    RETURN 'DQ batch ' || batch_id || ': ' || n_records || ' records, ' ||
           n_error || ' ERROR / ' || n_warn || ' WARN failures, ' || n_quar || ' quarantined.';
END;
$$;
